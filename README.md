# SNN-based network packet classifier (hardware firewall)

A spiking-neural-network classifier that decides, per packet and from headers
only, whether a frame is benign or malicious, and drops it before the software
stack processes it. One classification engine (`rtl/snn_classifier.v`) is used
in three deployments:

| target | variant | where the packet is stopped |
|---|---|---|
| **ASIC** (Cadence Genus/Conformal/Innovus at uni, Yosys + sky130 locally) | in-line, fused into the RX datapath of the open-source verilog-ethernet 1G MAC (`rtl/eth_mac_1g_snn_fifo.v`) | before the host FIFO/DMA, so the OS never sees it |
| **Tang Nano 9K** | the same in-line filter; PC ↔ USB-UART stands in for the PHY (`fpga/tang9k`) | inside the "NIC" (FPGA) |
| **Chameleon96** (USB WiFi on the HPS) | look-aside accelerator on the LW H2F bridge + kernel `rx_handler` hook (`rtl/snn_lookaside_avmm.v`, `sw/kmod`) | right after the WiFi driver, before the IP stack, sockets and apps |

```
              ┌──────────────────────────── snn_classifier ────────────────────────────┐
 bytes ──────►│ pkt_parser ─► spike_encoder (64 spikes + rate window) ─► FIFO ─► snn_core│──► verdict
              └──────────────────────────────────────────────────────────────────────────┘
 in-line:     MAC ─► snn_pkt_filter [circular buffer, commit/rollback, forward/drop] ─► host FIFO
 look-aside:  Linux rx_handler ─► 128-B header + true length ─► snn_lookaside_avmm ─► verdict ─► drop/pass
```

## Status (2026-10-13)

| item | state |
|---|---|
| Python golden model (parser, encoder, integer LIF SNN), QAT surrogate-gradient training | done |
| Synthetic labelled traffic (14 attack families) | done (99.7 % test, **synthetic, optimistic**) |
| Real-dataset loader (pcap/pcapng + UNSW-NB15 / CIC ground-truth CSV), `train.py --data` | done, round-trip verified. **Needs the pcaps** |
| RTL: parser, encoder, event-driven SNN core, shared classifier, in-line filter, look-aside wrapper | done |
| `sim/run_all.sh`: 7 regressions, all **PASS** (bit-exact vs golden model) | ✓ |
| verilog-ethernet MAC with firewall fused into RX path, GMII-level test | ✓ |
| Chameleon96: Platform Designer integration, **RBF built** (6 % ALMs, timing met @100 MHz, HPS handoff unchanged) | ✓, hardware test pending |
| Chameleon96: `snn_fw.ko` (built for 6.18.2-altera), `snn_fwctl` (static), firmware blob, Yocto layer | ✓ built, hardware test pending |
| Tang Nano 9K: open-source build, **bitstream built** (80 % LUT, 6 BSRAM, Fmax 57.6 MHz vs 27 MHz), PC demo script | ✓, hardware test pending |
| ASIC: Yosys + sky130 synthesis (snn_core 0.39 mm², 64 % of it the flop-based W1 memory) | ✓ area; timing needs OpenSTA/Cadence |
| ASIC: Genus / Conformal / Innovus scripts | written, run on the uni server |
| `snn_stdp.v` bugs fixed (saturation wrap etc.) + regression | ✓ |
| Chameleon96 on-board WiFi (SDIO via FPGA) | analysed, see `docs/chameleon96_wifi.md` |

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install numpy torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python model/train.py                 # synthetic data, ~20 s  -> model/params.json
.venv/bin/python model/export.py                # -> sim/vectors/ (cfg.txt, snn_fw.bin, golden vectors)
sim/run_all.sh                                  # all regressions (Questa + iverilog)

fpga/tang9k/build.sh prog                        # Tang Nano 9K: build + load (openFPGALoader)
python3 sw/host/tang_demo.py --port /dev/ttyUSB1 # replay vectors (or --pcap file.pcap), live verdicts
fpga/cv96_snn/build.sh                           # Chameleon96 RBF (Quartus 20.1 Lite)
make -C sw/kmod && make -C sw/tools              # kernel module + tool (Yocto toolchain)
asic/sky130/synth.sh snn_core                    # open ASIC synthesis (Yosys + sky130_fd_sc_hd)
```

Chameleon96 bring-up and attack demo: **`docs/chameleon96_deploy.md`**.

### Training on real captures

```bash
# UNSW-NB15: pcaps + NUSW-NB15_GT.csv
.venv/bin/python model/pcap_io.py 1.pcap 2.pcap --gt NUSW-NB15_GT.csv --format unsw --out data/unsw.npz
# CIC-IDS2017: pcap of a day + its labelled-flow CSV(s); CIC timestamps are local (UTC-3)
.venv/bin/python model/pcap_io.py Wednesday-workingHours.pcap --gt Wednesday*.csv --format cic --tz-offset-h 3 --out data/cic_wed.npz
.venv/bin/python model/train.py --data data/unsw.npz data/cic_wed.npz
.venv/bin/python model/export.py    # then rerun sims, reload weights on the boards (no re-synthesis needed)
```

## Classifier

**64 input spikes** (`model/pktfeat.py::FEATURE_NAMES`):
- Bias line.
- L3 type; L4 protocol; IHL class; DF/MF/fragment offset; TTL buckets; IP length buckets.
- Land, bogon source, broadcast destination.
- Six TCP flags plus NULL; dst/src port classes; TCP data offset; window; ICMP type.
- Payload-length buckets; length inconsistency; truncation; sensitive port; DNS.
- Stateful: pure-SYN and ICMP-echo counts over the last 32 frames, thresholds 8/16.

**Network:** 64 → 16 LIF → 2 LIF, int8 weights, 20-bit membranes, T = 8,
`v ← v − (v >>> 2) + I`, hard reset, TH1 = 256, TH2 = 128,
decision `cnt1 > cnt0 || (cnt1 == cnt0 && v1 > v0)`.

**Hardware.**
- Static input current is computed once per packet, visiting only active inputs (event-driven), one W1 row per cycle across all 16 neurons.
- The output layer is a pipelined, exactly-sized adder tree.
- Latency ≈ 30–40 cycles per packet.
- Weights live in runtime-writable memory (block RAM on FPGA, SRAM macro in ASIC), so retraining never needs re-synthesis.

### Register map (`snn_classifier`, word addresses)

| addr | | addr | |
|---|---|---|---|
| 0x001 / 0x002 | TH1 / TH2 | 0x010+h | W2[h] ([7:0] o0, [15:8] o1) |
| 0x003 | [3:0] T, [5:4] leak | 0x100+4·row+lane | W1 (4 × int8) |
| 0x004 | B2 | | |

In-line filter adds: 0x000 CTRL ([0] drop_en, [1] bypass) and 0x020–0x025 stats.
Look-aside adds: 0x400–0x41F header window, 0x420 SUBMIT, 0x421 VERDICT, 0x422 STATUS, 0x423 ID ("SNN2"), with stats at 0x020.

## Layout

```
model/   pktfeat.py snn_int.py (golden)  gen_traffic.py  pcap_io.py  train.py  export.py
rtl/     pkt_parser spike_encoder snn_core snn_classifier sync_fifo   (shared engine)
         snn_pkt_filter (in-line)  eth_mac_1g_snn_fifo (MAC fusion)  snn_pkt_filter_asic
         snn_lookaside_avmm (Chameleon96)  snn_fw_avmm (in-line over Avalon)  uart
sim/     testbenches + run_*.sh, run_all.sh, vectors/
fpga/    cv96_snn (Quartus project + Platform Designer component)  tang9k (open flow)  fit_check
sw/      kmod/snn_fw.c  tools/snn_fwctl.c  host/tang_demo.py  yocto/meta-snn  snn_regs.h
asic/    scripts (Genus, Conformal, Innovus, MMMC)  constraints  sky130 (Yosys)
docs/    chameleon96_deploy.md  chameleon96_wifi.md
snn_stdp/  original base design (fixed; original kept as src/snn_stdp_orig.v, tb/)
third_party/verilog-ethernet (MIT)
```

## Limitations / next steps

1. **Train and evaluate on real pcaps.** The synthetic accuracy is an upper bound.
2. The rate window counts frames, not time. Per-flow state would help with slow scans.
3. The ASIC needs SRAM macros for W1 and the packet buffer, plus closed timing on the Cadence flow.
4. 125 MHz on Cyclone V needs the precomputed-threshold LIF trick (currently 111 MHz standalone; the Chameleon96 runs at 100 MHz).
5. Optional: on-chip STDP adaptation (from `snn_stdp`) for drift.
