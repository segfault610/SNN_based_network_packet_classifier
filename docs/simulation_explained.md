# The simulation, explained

This explains what the xrun run (`RESULT: PASS (10 tests)`) actually proves: the test vectors, the testbench, each
of the 10 tests, and how to read the SimVision waveform. For the compact test table, see
`docs/functional_verification.md`.

## 1. What is being tested

The chip under test is **`snn_pkt_filter_asic`** (`rtl/snn_pkt_filter_asic.v`). It is the firewall block that sits
between an Ethernet MAC and the host.

```
 Ethernet MAC ──s_axis──►  [ packet buffer 2 KiB ] ──────────────────────► m_axis ──► host (OS)
 (bytes in)                 │                          ▲ forward or discard
                            └─► parser ─► encoder ─► SNN ─► verdict ┘
                                (header    (64 yes/no   (64→16→2 spiking
                                 fields)    "spikes")    neurons)
```

- Bytes arrive one per clock (8 ns, 125 MHz, the speed of 1 Gb/s Ethernet). The chip can never say "wait" to the
  MAC (`s_axis_tready` is always 1).
- While a frame is being stored, its header is turned into 64 binary features ("spikes"). The spiking neural network
  then decides whether the frame is **benign** or **malicious**.
- Once the verdict is known, a benign frame is sent to the host byte for byte. A malicious frame is erased from the
  buffer, so the host never sees it. That is the "preventive" part.

## 2. Where the "right answers" come from: the golden model

The Python files in `model/` are the **reference implementation** (the "golden model"):

| file | role |
|---|---|
| `pktfeat.py` | parses a frame and produces the same 64 spikes as the hardware (+ the SYN/ICMP rate window) |
| `snn_int.py` | the same integer spiking network as the RTL: same int8 weights, same shifts, same rounding |
| `gen_traffic.py` | generates labelled synthetic traffic: benign flows plus 14 attack types |
| `train.py` | trains the weights (quantisation-aware, so the integer version keeps the accuracy) → `params.json` |
| `export.py` | writes the test vectors that the testbench uses |

The hardware must give **exactly** the same answer as `snn_int.py` for every frame: the same spikes, the same
neuron spike counts, the same verdict. That is what "bit-exact" means in the log. It also means the hardware
reproduces the model's mistakes. A frame the model gets wrong, the hardware gets wrong in exactly the same way,
and that still counts as a pass, because the testbench checks the **implementation**. How good the
**classifier** is gets measured separately (section 6).

## 3. The test vectors (`sim/vectors/`)

`.venv/bin/python model/export.py` (600 frames, seed 7) writes:

| file | content | used by |
|---|---|---|
| `cfg.txt` | 276 lines `addr data`: the trained network as config-bus writes | testbench, `tang_demo.py`, `snn_fwctl load` |
| `frames.txt` | 600 lines `length byte0 byte1 …`: complete Ethernet frames (no preamble/FCS) | testbench input |
| `expected.txt` | 600 lines `spikes cnt0 cnt1 mal label kind`: golden answer + ground truth per frame | testbench checks |
| `snn_fw.bin` | `cfg.txt` in binary, for the Linux kernel module | Chameleon96 |
| `w1.hex` | hidden-layer weights for memory init | FPGA option |

### 3.1 `cfg.txt`: the trained network as 276 register writes

| address | value (example) | meaning |
|---|---|---|
| `001` | `00000100` | TH1 = 256: firing threshold of the 16 hidden neurons |
| `002` | `00000080` | TH2 = 128: firing threshold of the 2 output neurons |
| `003` | `00000028` | T = 8 time steps, leak = 2 (membrane loses 1/4 each step) |
| `004` | `0000282b` | output biases, one int8 per output neuron |
| `010`–`01f` | 16 words | W2: weights hidden → output (2 × int8 per hidden neuron) |
| `100`–`1ff` | 256 words | W1: weights input → hidden, 64 inputs × 16 neurons × int8, 4 per word. The last write is `1ff 052d54cf` (input 63, neurons 12–15); you can see it in the waveform every time the weights are reloaded |

4 + 16 + 256 = 276 writes. Weights are loaded at run time, so retraining never needs a new chip or bitstream.

### 3.2 `frames.txt`: the traffic

The first frame, decoded:
```
98 02 98 ca d7 1a  9d 02 9b 7f c2 df  08 00 | 45 00 00 54 … 40 01 … c0 a8 03 c8  88 b9 4b b1 | 08 00 …
 destination MAC    source MAC        IPv4    IP hdr, length 84, TTL 64, proto 1 (ICMP),  ICMP type 8 = ping request
                                              192.168.3.200 → 136.185.75.177
```

The 600 frames form one continuous, time-ordered capture. The order matters, because the rate window counts SYN and
ping frames over the last 32 frames:

| frames | content | count |
|---|---|---|
| 0–46 | benign background (TCP sessions, DNS, pings, ARP, IPv6, …) | 47 |
| 47–247 | **SYN flood** episode: TCP SYNs to one victim, interleaved with background | 153 attack + 48 benign |
| 260–276 | **port-0** probes (TCP/UDP to port 0, invalid) | 4 attack + 13 benign |
| 341–589 | **ACK scan** (TCP ACK probes across ports, used to map firewalls) | 41 attack + 208 benign |
| rest | benign | |
| **total** | **402 benign, 198 malicious** | 600 |

> **Limitation.** This vector set contains only **3 of the 14** attack types the generator knows: SYN flood, port 0
> and ACK scan. It is a single 600-frame draw. The training and test sets in `train.py` contain all 14 (port
> scans: SYN/NULL/Xmas/FIN/SYN-FIN/ACK/Maimon; UDP scan, land, ping of death, ICMP flood, smurf, tiny fragments,
> teardrop, malformed headers, bogon spoofing, port 0, DNS amplification, low-TTL evasion). The hardware
> data path is the same for every type, so the coverage is fine for proving the **implementation**. To also see
> every attack type in simulation, export a longer stream, e.g. `model/export.py 4000`, then rerun.

### 3.3 `expected.txt`: the golden answer per frame

```
0022000000111283 4 0 0 0 benign
└── spikes ────┘ │ │ │ │ └ attack type (for the reader only)
                 │ │ │ └ label: ground truth from the generator (0 benign, 1 malicious)
                 │ │ └ mal: the golden model's verdict, which the hardware must reproduce
                 │ └ cnt1: how often the "malicious" output neuron fired in the 8 time steps
                 └ cnt0: how often the "benign" output neuron fired
```
Verdict rule: malicious if `cnt1 > cnt0`, or, when they are equal, if the malicious neuron's membrane is higher.

The spike word for frame 0 is `0x0022000000111283`. Its set bits are:

| bit | feature |
|---|---|
| 0 | bias |
| 1 | IPv4 |
| 7 | ICMP |
| 9 | IP header length 5 |
| 12 | DF flag |
| 16 | TTL 9–64 |
| 20 | IP length 41–100 |
| 49 | ICMP echo request |
| 53 | payload 9–64 bytes |

In other words, "an ordinary ping". The benign neuron fired 4 times and the malicious one 0 times, so it's benign.
All 64 feature names are in `model/pktfeat.py::FEATURE_NAMES`. Bits 57–60 are the stateful rate features (SYN /
ICMP-echo counts in the last 32 frames ≥ 8 or ≥ 16); they are what makes a flood detectable even though every
single SYN looks harmless on its own.

## 4. How the testbench works (`sim/asic/tb_snn_asic.sv`)

- **Plays the MAC.** It sends each frame byte by byte, with no gaps inside a frame. Between frames it waits a
  gap (the inter-frame gap, IFG) whose length each test chooses.
- **Plays the host.** It drives `m_axis_tready` randomly (e.g. 90 % of cycles ready) to imitate a host that is
  sometimes busy. It collects every byte that comes out and reassembles the frames.
- **Plays the CPU.** It writes and reads registers over the `cfg_*` bus: loads `cfg.txt`, sets the mode, reads
  the counters.
- **Only uses the chip's pins**, never internal signals. So the very same file also runs on the gate-level
  netlists from Genus and Innovus.
- **Changes inputs on the falling clock edge and samples outputs on the falling edge.** The chip works on the rising
  edge, so there is never a race between testbench and chip, even with real gate delays (SDF).
- **Is self-checking.** Every mismatch prints `[ERR] …`, each test prints `PASS` or `FAIL`, and the end prints
  `RESULT`. A FAIL is not possible to miss.

The chip's own counters, read at the end of each test, are checked as well:

| register | counter |
|---|---|
| `0x020` | frames committed (accepted into the buffer) |
| `0x021` | frames dropped at ingress (bad checksum, too big, or no room) |
| `0x022` | frames classified malicious |
| `0x023` | frames forwarded to the host |
| `0x024` | frames blocked |
| `0x025` | last verdict `{mal, cnt1, cnt0}` |

## 5. The 10 tests: what each one proves

| test | what happens | what it proves | your run |
|---|---|---|---|
| **T1 Reset** | reset, then read every register | the chip wakes up in a safe, known state: blocking on, default thresholds, counters 0, never stalls the MAC | PASS |
| **T2 Config** | write the 276 weight words, read back the readable ones | the CPU can load and verify a network | PASS |
| **T3 Golden run** | all 600 frames in blocking mode, random gaps 12–40 cycles, host 90 % ready | the core proof: every one of 600 verdicts equals the Python model; exactly the 403 benign-verdict frames come out, byte-identical and in order; the 197 malicious-verdict frames never come out | PASS: 197 blocked, 403 forwarded |
| **T4 Monitor mode** | `CTRL = 0`, frames 0–149 | "detect but don't block" (for checking false alarms on a real network first): still classifies, still counts, but forwards all 150 | PASS: 78 flagged, 150 forwarded |
| **T5 Bypass** | `CTRL.bypass = 1`, frames 0–149 | the emergency "firewall off" switch passes everything | PASS |
| **T6 Corrupted frames** | 100 frames, every 5th marked bad-checksum by the MAC (`s_axis_tuser`) | a damaged frame is erased completely: no verdict, never forwarded, counted as dropped; its neighbours are unaffected | PASS: 20 dropped, 80 committed |
| **T7 Size limits** | a 2148-byte frame (bigger than the 2 KiB buffer), an 8-byte runt, a 1518-byte maximum Ethernet frame, then 10 normal frames | too-big frames are dropped whole and the buffer recovers; tiny and maximum-size frames pass through intact | PASS |
| **T8 Line rate** | 250 frames back-to-back with only 20 idle cycles between them | the classifier keeps up with full 1 Gb/s traffic of minimum-size frames: zero drops, still bit-exact | PASS |
| **T9 Overload** | 600 frames with 1–3 cycle gaps (faster than Ethernet allows) while the host is only 35 % ready | when the chip **must** drop, it drops whole frames, never half frames; nothing is corrupted, duplicated or reordered; all counters add up | PASS: about 1/3 dropped (the number depends on the simulator's random sequence) |
| **T10 Reset during traffic** | reset while a frame is half received and another is half sent; reload; 60 frames | reset cleanly aborts both, clears counters and the rate window, and the chip then works perfectly again | PASS |

### Detection numbers in T3

The log line `TP=197 FP=0 TN=402 FN=1` compares the verdicts against the **ground-truth labels**:

| | meaning | count |
|---|---|---|
| TP (true positive) | attack, flagged | 197 |
| FP (false positive) | benign, flagged (a false alarm: a legitimate packet blocked) | 0 |
| TN (true negative) | benign, passed | 402 |
| FN (false negative) | attack, missed | 1 |

The one miss is **frame 128**, a SYN-flood packet. The network's output neurons fired `cnt0 = 4` (benign) vs
`cnt1 = 2` (malicious), so it was passed. The Python model makes the same decision, so the hardware is correct to
reproduce it. Accuracy on this set is 599/600 = 99.8 %.

> These detection numbers come from **synthetic** traffic, so they are optimistic. Real accuracy has to come from
> real captures (UNSW-NB15 / CIC-IDS2017 pcaps via `model/pcap_io.py`, then retrain and re-export). The 10 tests
> stay exactly the same; only the vectors change.

## 6. Two different questions, kept apart

| question | answered by | status |
|---|---|---|
| Does the hardware do exactly what the model does, under every circumstance (modes, errors, overload, reset)? | **this simulation** (T1–T10, bit-exact) | **yes**: RTL (xrun + Questa), sky130 gate level (Questa) |
| Is the model good at spotting real attacks? | training/evaluation in `model/` on real datasets | synthetic only so far |

## 7. Reading the SimVision waveform

![xrun RTL run in SimVision: all top-level ports over the full 3.2 ms run, RESULT: PASS (10 tests)](img/xrun_rtl_waveform.png)

*xrun + SimVision on the uni Cadence server, RTL, all ten tests. The cursor (TimeA = 1.795 ms) sits in T7.
The run ends at 3,200,784 ns.*

Ports in the waveform:

| signal | meaning |
|---|---|
| `clk`, `rst` | 125 MHz clock, synchronous reset |
| `s_axis_tdata[7:0]`, `s_axis_tvalid`, `s_axis_tlast` | bytes from the MAC; `tlast` marks the final byte of a frame |
| `s_axis_tuser` | MAC says "this frame had a bad checksum" (only in T6) |
| `s_axis_tready` | always 1: the firewall never stalls the MAC |
| `m_axis_tdata`, `m_axis_tvalid`, `m_axis_tlast` | bytes going to the host (forwarded frames only) |
| `m_axis_tready` | the host is ready; random in T3–T5, T9, T10 and constant 1 in T6–T8 |
| `m_axis_tuser` | always 0 |
| `verdict_valid` | one-cycle pulse per classified frame |
| `verdict_mal` | high together with `verdict_valid` when that frame was judged malicious |
| `cfg_wr`, `cfg_rd`, `cfg_addr`, `cfg_wdata`, `cfg_rdata` | the CPU register bus |

Timeline of the full run (total 3.2 ms simulated):

| time (ms) | test | what to look for |
|---|---|---|
| 0 – 0.01 | T1, T2 | `cfg_*` activity only, no frames |
| 0.01 – 1.03 | T3 | dense traffic; `verdict_mal` bursts during the SYN flood (frames 47–247, early part) |
| ≈ 1.03 | T4 | `cfg_addr = 000`, `cfg_wdata = 0`: blocking off |
| ≈ 1.27 | T5 | `cfg_wdata = 3`: bypass |
| 1.51 – 1.69 | T6 | the only `s_axis_tuser` pulses in the run |
| ≈ 1.70 – 1.80 | T7 | one very long input frame (2148 bytes) and no output for it |
| ≈ 1.80 – 2.09 | T8 | very regular frames, `m_axis_tready` flat at 1 |
| 2.09 – 3.1 | T9 | input almost continuous, output throttled, many frames never appear at `m_axis` |
| 3.13 – 3.20 | T10 | reset pulse, counters read `00000000`, weights reloaded (`1ff 052d54cf`), 60 frames |

Each reset is followed by a reload of `cfg.txt` (`cfg_addr` runs 001 … 1ff), because reset clears the thresholds
and output weights.

### Useful internal signals to add (RTL run)

To see the network working, open `tb_snn_asic.dut.u_filter.u_cls` in the Design Browser and add:

| signal | what it shows |
|---|---|
| `spikes[63:0]` + `spk_valid` | the 64 features of each frame |
| `u_core.state` | idle → accumulate input current → 8 LIF time steps → output |
| `u_core.cnt[0:1]`, `u_core.v1[*]`, `u_core.v2[*]` | output spike counts, hidden / output membranes |
| `dut.u_filter.verd_push`, `c_mal`, `c_cnt0`, `c_cnt1` | the verdict as it is produced |
| `dut.u_filter.wr_ptr`, `rd_ptr` | buffer fill level; it rises and rolls back in T6, T7 and T9 |

(These internal names exist only in the RTL. In gate-level netlists, use the ports.)

## 8. Where the other simulations fit

| script | design | what it adds |
|---|---|---|
| `sim/asic/run.sh filter` | same filter, FPGA buffer size | also compares every 64-bit spike vector (internal signal) |
| `sim/asic/run.sh mac` | filter inside the open-source Ethernet MAC | real GMII pins: preamble, checksum, MAC framing |
| `sim/asic/run.sh suite-gl` | this suite on a synthesized sky130 netlist | gates instead of RTL, X-propagation from real cell models |
| `sim/tang9k/run.sh rtl`, `gl` | Tang Nano 9K top | the same filter fed over UART/SLIP from a PC, RTL and synthesized netlist |
| `sim/tang9k/run.sh host` | PC demo script vs a software board | `tang_demo.py` works before you touch hardware |
| `sim/cv96/run.sh lookaside` | Chameleon96 accelerator | the register sequence the Linux kernel module uses: header window, submit, poll verdict |

All of them use the same `sim/vectors/` and the same golden model. A change to the model or weights is therefore
checked everywhere by `sim/run_all.sh`.
