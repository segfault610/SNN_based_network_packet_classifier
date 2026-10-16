# How the network is trained

The hardware (`snn_core`) is fixed logic; the only thing that makes it classify well is its **weights** — the int8
numbers `W1`, `W2`, `B2` loaded over the config bus. This document explains where those numbers come from: the
training data, the method, the result, and the honest limitations. Everything here is in `model/train.py`.

## 1. The short answer (for a viva)

> "We train it offline in PyTorch with **quantisation-aware, surrogate-gradient** learning. The training forward
> pass reproduces the integer hardware exactly — int8 weights, the arithmetic-shift leak, the hard reset — so the
> learned weights run bit-identically on the FPGA with no retraining or fine-tuning. We train on **labelled packet
> headers**: currently a synthetic generator of normal traffic and 14 attack families; the pipeline also loads real
> captures (UNSW-NB15 / CIC-IDS2017). We then quantise the weights, write them to `params.json`, and the Python
> golden model, every RTL simulation and the FPGA all agree bit-for-bit (verified)."

## 2. What is actually trained

Only three small int8 tables, ~1.1 KB total:

| parameter | shape | meaning |
|---|---|---|
| `W1` | 64 × 16 | input feature → hidden neuron weights |
| `W2` | 16 × 2 | hidden neuron → output neuron weights |
| `B2` | 2 | output-neuron biases |

The thresholds (`TH1=256`, `TH2=128`), time steps (`T=8`) and leak (`÷4`) are **fixed by design**, not trained.
The 64 input features themselves are **hand-designed rules** (in `pkt_parser`/`spike_encoder`), not learned — the
network only learns how to *weigh* them. So "training" means: find the 1,186 int8 numbers that best separate benign
from malicious given those 64 features.

## 3. The training data

### 3.1 What one training example is

A training example is **(64 header features, label)** — not a raw packet. For every frame we:
1. parse the header (`model/pktfeat.py::parse`, mirrors `rtl/pkt_parser.v`),
2. encode it to 64 binary features (`encode`, mirrors `rtl/spike_encoder.v`), including the stateful 32-frame
   SYN/ping rate window,
3. attach the ground-truth label: `0` benign, `1` malicious.

Because the rate features are stateful, frames are encoded **in arrival order**, as a stream, exactly as the
hardware sees them.

### 3.2 The synthetic generator (current default)

`model/gen_traffic.py` builds a realistic, time-ordered traffic stream: benign background flows (TCP sessions, DNS,
pings, ARP, IPv6, legitimate fragments) interleaved with **attack episodes**. Each generated frame is a real,
checksummed Ethernet/IP/TCP/UDP/ICMP packet, and its label is known because the generator made it. The 14 attack
families (each a separate `_` method):

| | | |
|---|---|---|
| SYN flood | port scans: SYN/NULL/Xmas/FIN/SYN-FIN/ACK/Maimon | UDP scan |
| land | ping of death | ICMP flood |
| smurf | tiny fragments | teardrop |
| malformed headers (bad IHL/data-offset/length) | bogon-source spoofing | port 0 |
| DNS amplification | low-TTL evasion | |

Sizes used for `params.json`:

| set | frames | source |
|---|---|---|
| train | **60,000** | `gen_traffic.Gen(seed=1)` |
| validation | **20,000** | `seed=2` |
| test | **20,000** | `seed=3` (different seed = unseen traffic) |

The three sets use different random seeds, so the test set is traffic the network never saw during training.

### 3.3 Real captures (same pipeline, for a stronger result)

`model/pcap_io.py` reads pcap/pcapng and labels each packet from the dataset's ground-truth CSV by 5-tuple + time,
for **UNSW-NB15** and **CIC-IDS2017**. Then:
```bash
.venv/bin/python model/pcap_io.py day.pcap --gt labels.csv --format cic --out data/cic.npz
.venv/bin/python model/train.py --data data/cic.npz        # chronological 70/15/15 split
.venv/bin/python model/export.py                           # re-export weights; no re-synthesis needed
```
The real-data split is **chronological** (first 70 % train, next 15 % val, last 15 % test), which is the honest way
to evaluate an IDS: train on the past, test on the future. This is the planned next step; the shipped `params.json`
is still synthetic (see §6).

## 4. The training method

### 4.1 The hard part: spikes have no gradient

A spiking neuron's output is a step: fire (1) or not (0). A step has zero derivative almost everywhere, so ordinary
back-propagation can't flow through it. The standard fix (Neftci et al. 2019, in `Papers/`) is a **surrogate
gradient**: use the true step on the *forward* pass, but a smooth, differentiable curve on the *backward* pass. In
`model/train.py::Spike` the backward gradient is `1 / (a·(1+|x|/a)²)` (a fast-sigmoid surrogate). The network is
then trained like any other with Adam.

### 4.2 Quantisation-aware: train what you deploy

The key property is that **the training forward pass is the integer hardware**, not a float approximation:

- **int8 weights** via straight-through rounding: `ste_round` rounds and clamps to [−128, 127] on the forward pass,
  but passes the gradient through unchanged, so the optimiser learns weights that are *already* good after rounding.
- **the leak is an arithmetic shift**: `v − floor(v / 4)`, via `ste_floor`, exactly `v - (v>>>2)` in Verilog.
- **hard reset to 0** on a spike, 8 time steps, thresholds 256/128 — identical to `rtl/snn_core.v` and
  `model/snn_int.py`.

So there is **no accuracy lost between training and the chip**: the float model, the integer golden model, every
RTL simulation and the FPGA produce the same verdict for the same frame. We verified this bit-exactly (600/600 test
frames, and the custom-traffic cross-check in `sim/run_all.sh`).

### 4.3 Hyperparameters (in `model/train.py`)

| | value |
|---|---|
| optimiser | Adam, lr 1.0, cosine-annealed over 40 epochs |
| batch size | 256 |
| loss | cross-entropy on `cnt + 0.5·v₂/TH2` (spike counts, with the leftover membrane as a tie-breaker so gradients flow even at 0 spikes) |
| class weighting | `√(n_benign / n_malicious)` on the malicious class, so the rarer attacks aren't ignored |
| weight init | `N(0, 30)` (large, because they will be rounded to int8) |
| seed | fixed (`torch.manual_seed(0)`) → reproducible |

Training takes about 20–30 s on a laptop CPU (no GPU needed; the network is tiny).

## 5. The result (synthetic data, stored in `params.json`)

| set | accuracy | detection rate (TPR) | false-positive rate |
|---|---|---|---|
| validation (20k) | 99.71 % | 99.21 % | 0.19 % |
| **test (20k, unseen)** | **99.76 %** | **99.41 %** | **0.19 %** |

Per-attack-family detection on the test set is 100 % for most families (all scan types, land, smurf, teardrop,
ping-of-death, tiny fragments, TTL evasion, bogon spoofing). The weak spots are **`malformed_doff` (50 %)** — a bad
TCP data-offset that the current features barely capture — and small dips on `dns_amp` (97 %) and `syn_flood`
(99.3 %). Benign accuracy is 99.8 %.

Reproduce: `.venv/bin/python model/train.py` (prints these numbers and writes `params.json`).

## 6. Honest limitations (say these before the prof does)

1. **The headline numbers are on synthetic traffic**, so they are an *upper bound*. Real networks are messier; expect
   lower accuracy and more false positives. Retraining on UNSW-NB15 / CIC-IDS2017 (§3.3) is the planned next step.
2. **The generator can teach shortcuts.** The model leans on the IP "don't fragment" flag because the synthetic
   benign TCP always sets it; and a flood of *normal-looking* SYNs isn't caught (see `docs/custom_traffic_cv96.md`
   §5). These are artefacts of synthetic data, not of the SNN, and real data fixes them.
3. **Header-only, by design.** It never sees payload, so it cannot catch content attacks, a wrong password, or
   malware in a file (see `docs/custom_traffic_cv96.md` §1). It is a scan/flood/malformed-header detector.
4. **The 64 features are hand-designed**, not learned. A different attack that doesn't move any of the 64 features
   would be invisible until a new feature is added (which is an RTL change, not just retraining).

## 7. From trained weights to the chip (no re-synthesis)

```
model/train.py            -> params.json         (the trained int8 weights + the fixed config)
model/export.py           -> sim/vectors/cfg.txt (276 config-bus writes)   and   snn_fw.bin (binary, for Linux)
load at run time:
  board : snn_fwctl load cfg.txt   /   snn_fw.ko loads snn_fw.bin
  RTL   : the testbenches write cfg.txt over the config bus
```

Because weights live in run-time-writable registers/RAM, **retraining never needs a new bitstream or a new chip** —
you re-run `train.py` + `export.py` and reload 276 numbers. This is the whole reason the weights are config, not
hard-wired.

See also: `docs/design.md` (the 64 features, the register map), `docs/neuron_hdl.md` (the hardware), and
`model/explain_frame.py` (what the trained weights do for any single frame).
