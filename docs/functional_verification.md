# Functional verification (xrun / Xcelium)

**DUT:** `snn_pkt_filter_asic`, the ASIC top. It is the in-line firewall with a 2 KiB packet buffer and a 64→16→2 SNN.

**Testbench:** `sim/asic/tb_snn_asic.sv`. A plain-language walk-through of the vectors, tests and waveform is in `docs/simulation_explained.md`.
- It is self-checking and uses only the top-level ports.
- It drives inputs and samples outputs on the falling clock edge, so the same file runs unchanged on:
  - the RTL;
  - the Genus `tm_netlist` (zero-delay gate-level simulation);
  - the Innovus netlist with post-route SDF.

**Reference:** the Python golden model (`model/`). `model/export.py` writes the trained weights (`cfg.txt`), 600 frames (`frames.txt`) and the bit-exact expected verdict per frame (`expected.txt`) to `sim/vectors/`.

## How to run

```bash
cd asic
scripts/run_flow.sh sim-rtl                       # RTL
CELL_V=<gsclib090 cells .v> scripts/run_flow.sh sim-gls   # Genus tm_netlist_optimal, zero delay
CELL_V=<gsclib090 cells .v> scripts/run_flow.sh sim-sdf   # Innovus netlist + post-route SDF
# by hand:
xrun -F scripts/xrun_rtl.f -input scripts/xrun_batch.tcl +VEC_DIR=$PWD/../sim/vectors
xrun -F scripts/xrun_rtl.f -input scripts/xrun_waves.tcl +VEC_DIR=$PWD/../sim/vectors -access +rwc ; simvision waves.shm
```
Locally with Questa: `sim/asic/run.sh suite` for RTL, `sim/asic/run.sh suite-gl` for the Yosys → sky130 gate-level netlist.

## Result on the uni server (xrun, RTL)

![SimVision waveform of the passing xrun run](img/xrun_rtl_waveform.png)

`RESULT: PASS (10 tests)`, ending at 3,200,784 ns. The timeline is explained in `docs/simulation_explained.md` §7.

## Expected xrun output

Logs are written to `asic/out/<DESIGN>/sim/xrun_*.log`. The numbers below are for the current `sim/vectors/` (synthetic traffic). They change if you retrain and re-export, and the result must still be PASS.

```
[TB] 600 frames, 276 config words
[T1 reset values]
  PASS T1 reset values
[T2 config write / readback]
  PASS T2 config write / readback
[T3 golden model, bit-exact (drop mode, all vectors)]
    frames=600 mal=197 forwarded=403 blocked=197
    vs ground truth: TP=197 FP=0 TN=402 FN=1
  PASS T3 golden model, bit-exact (drop mode, all vectors)
[T4 monitor mode CTRL.drop_en=0 (classify, forward all)]
    frames=150 mal=78 forwarded=150 blocked=0
  PASS T4 ...
[T5 bypass CTRL.bypass=1 (forward all)]
    frames=150 mal=78 forwarded=150 blocked=0
  PASS T5 ...
[T6 bad-FCS frames (tuser on last beat) dropped whole]
    sent=100 bad=20 committed=80 forwarded=48 blocked=32
  PASS T6 ...
  PASS T7 oversized (> buffer), runt and 1518-byte frames
[T8 back-to-back burst, minimum IFG, 250 frames]
    frames=250 mal=152 forwarded=98 blocked=152
  PASS T8 ...
[T9 egress back-pressure 35% + IFG 1..3 (forces ingress drops)]
    sent=600 committed=398 dropped=202 forwarded=275 blocked=123
  PASS T9 ...
[T10 reset in mid-frame / mid-egress, then recovery]
    frames=60 mal=11 forwarded=49 blocked=11
  PASS T10 ...
============================================================
 RESULT: PASS (10 tests)
```

**Notes on the numbers:**
- **T9:** the exact split between `committed` and `dropped` depends on the simulator's random sequence, because the TB uses `$urandom` for back-pressure and gaps. xrun and Questa produce different values; only the consistency checks matter.
- **Simulated time:** about 3.2 ms.
- **Wall time (Questa on this laptop):** RTL about 2 s; gate-level (about 100 k cells) about 1 min. Expect the same order of magnitude from xrun.
- **Any failure:** prints `[ERR] ...` lines under the failing test, then `RESULT: FAIL (n errors)`.

## Test table

**Common setup.** Clock: 125 MHz (8 ns), the 1 GbE GMII byte clock. Frames are driven MAC-style: no gaps inside a frame, and `tuser` (bad FCS) is only valid on the last beat. "Golden" means the per-frame verdict sequence, the forwarded frames (byte by byte) and the hardware counters all match the Python model exactly.

| # | scenario | stimulus | expected design behaviour | pass criteria |
|---|---|---|---|---|
| T1 | **Power-on reset** | 10-cycle synchronous reset, then read every register | `s_axis_tready` = 1 (the MAC is never stalled); no output activity; CTRL = drop_en; TH1 = 256, TH2 = 128, T = 8, leak = 2; W2/B2 = 0; all counters 0; unmapped addresses read 0 | exact register values, outputs idle |
| T2 | **Configuration bus** | write the trained weights (276 words: TH, TIMING, B2, 16×W2, 64×4 W1), read back every non-W1 register, toggle CTRL | registers hold what was written. W1 is write-only (it is a memory) | readback = written value |
| T3 | **Normal operation, drop mode** | all 600 frames (mixed benign traffic + 14 attack families), random gap 12–40 cycles, 90 % egress ready | one verdict per frame, in order. Benign frames are forwarded unchanged; malicious frames are discarded from the buffer and never appear at `m_axis` | verdicts and forwarded frames bit-exact with the golden model; counters: committed 600, ingress drops 0, mal = forwarded-out count, forwarded + blocked = committed; last-verdict register = the golden {mal, cnt1, cnt0} of the final frame |
| T4 | **Monitor mode** (`CTRL = 0`) | reset, reload weights, frames 0–149 | still classifies (verdict pulses, mal counter, LED/IRQ use), but forwards **every** frame. Used to measure false positives before enabling blocking | verdicts golden, all 150 frames forwarded byte-exact, blocked = 0 |
| T5 | **Bypass** (`CTRL.bypass = 1`) | same as T4 | same as monitor mode: forward everything, still classify and count | as T4 |
| T6 | **Corrupted frames** (bad FCS, `tuser` = 1 on last beat) | 100 frames, every 5th marked bad | a bad frame is rolled back out of the buffer: no verdict, never forwarded, counted as an ingress drop. Good frames around it are unaffected | ingress drops = 20, committed = 80, verdicts = 80, egress is an in-order subset of the good frames only |
| T7 | **Frame-size limits** | 2148-byte frame (larger than the 2 KiB buffer), 8-byte runt, 1518-byte max-size frame, then 10 normal frames (monitor mode) | an oversized frame is dropped whole at ingress (it can't be stored, and the MAC can't be stalled), and the buffer recovers. Runts and max-size Ethernet frames are classified and forwarded intact | ingress drops = 1, committed = 12, 12 verdicts, all 12 frames out byte-exact and in order |
| T8 | **Line rate** | 250 frames back-to-back with 20 idle cycles between frames (harsher than real GMII: 12 B IFG + 8 B preamble + 4 B FCS = 24), 100 % egress ready | classification keeps up with minimum-size frames at 1 Gb/s: no drops, no added gaps | golden, ingress drops = 0 |
| T9 | **Overload** (host side slow) | all 600 frames with 1–3 cycle gaps (beyond line rate) and only 35 % egress ready | buffer / classifier queue fill up. Whole frames are dropped at ingress, never partial frames. Nothing is corrupted, duplicated or reordered, and the counters stay consistent | committed + dropped = 600, forwarded + blocked = committed, verdict pulses = committed, egress count = forwarded counter, egress is an in-order subset of the input, some drops > 0 |
| T10 | **Reset during traffic** | 6 frames with 20 % egress ready (egress busy), half of a 7th frame, then reset; reload weights, 60 frames | reset aborts the half-received frame and the frame being sent (`m_axis_tvalid` drops at once), clears all counters and the rate window, and the design resumes cleanly | `m_axis_tvalid` = 0 during reset, counters 0, then golden for frames 0–59 |

## Design behaviour summary (what the tests establish)

| circumstance | behaviour |
|---|---|
| benign frame | forwarded unchanged after its verdict (store-and-forward, so latency is about frame length + ~40 cycles) |
| malicious frame, `drop_en = 1` | discarded inside the buffer; the host never sees a byte of it; `blocked` and `mal` counters increment; `verdict_mal` pulses |
| malicious frame, monitor / bypass | forwarded, but still flagged (`verdict_mal`, `mal` counter) |
| bad FCS (`tuser`) | dropped whole, no verdict, `dropped_ingress` + 1 |
| frame > 2048 B (ASIC buffer) | dropped whole, `dropped_ingress` + 1. Jumbo frames need a bigger `BUF_AW` |
| frame ≤ 14 B (runt) | classified (truncation feature) and handled like any other frame |
| host back-pressure / burst beyond line rate | ingress drops of whole frames once the buffer or feature queue (4 frames) is full; never back-pressures the MAC; ordering preserved |
| minimum-size frames at 1 Gb/s | sustained, no drops |
| after reset, before weights are loaded | W2/B2 = 0, so no output neuron can fire: every frame is classified benign and forwarded (fail-open) |
| reset | synchronous; clears counters, control and thresholds, the rate window and both pointers. W1 is a memory and is **not** cleared, so always reload the full `cfg.txt` after reset |
| weights reloaded at run time | take effect on the next classified frame; no re-synthesis needed |
| SYN / ICMP-echo floods | the rate window (last 32 frames, thresholds 8/16) raises the flood features; visible in T3/T8 as bursts of `mal` verdicts |

## Other regressions (Questa, `sim/run_all.sh`)

| testbench (script, mode) | what it adds |
|---|---|
| `sim/asic/tb_snn_pkt_filter.sv` (`sim/asic/run.sh filter`, `stress`) | same filter with the FPGA buffer size; also checks every 64-bit **spike vector** against the golden model (needs hierarchical access, so RTL only); stress mode |
| `sim/asic/tb_eth_mac_snn.sv` (`sim/asic/run.sh mac`) | filter fused into the verilog-ethernet `eth_mac_1g` RX path, driven at the **GMII** pins (preamble, FCS) |
| `sim/cv96/tb_snn_lookaside.sv`, `tb_snn_fw_avmm.sv` (`sim/cv96/run.sh lookaside`, `avmm`) | Avalon-MM wrappers; the Chameleon96 look-aside accelerator (128-B header window, SUBMIT/VERDICT registers, IRQ) |
| `sim/tang9k/tb_tang9k.sv` (`sim/tang9k/run.sh rtl`, `gl`) | Tang Nano 9K top through UART + SLIP, RTL and the Yosys/Gowin netlist |

## Not covered (known gaps)

- Formal property checks. Code coverage collection: add `-coverage all -covoverwrite` to the xrun command and open the result with `imc`.
- Writing config registers while frames are in flight. This is allowed, but the frame being classified at that moment may see the old or the new weights.
- Accuracy on real traffic: the current vectors come from the synthetic generator. Retrain with real pcaps (`model/pcap_io.py`) and re-export; the tests stay the same.
