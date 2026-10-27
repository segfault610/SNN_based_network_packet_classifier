# Implementation reports (area / timing / power)

All synthesis and place-and-route reports for the SNN packet classifier, in one place, with a comparison to the
literature. Numbers are copied from the actual tool reports (paths given per section). The source `.rpt`/`.summary`
files are committed in the repo.

**Quick answer — does each flow report area / timing / power?**

| flow | area | timing | power |
|---|---|---|---|
| sky130 synthesis (Yosys) | ✓ cell area | ✗ (STA not run in the open synth script) | ✗ |
| sky130 place & route (OpenROAD) | ✓ die + cell area | ✓ multi-corner | ✓ (vectorless estimate) |
| **FPGA Quartus (Cyclone V)** | **✓ resources (ALM/reg/RAM/DSP)** | **✓ Fmax / slack** | **✗ PowerPlay not run** |
| FPGA Tang Nano 9K (nextpnr) | ✓ LUT/DFF/BSRAM | ✓ Fmax | ✗ (no open power tool for Gowin) |
| Cadence 90 nm (Genus/Innovus) | ✓ | ✓ | ✓ | *(run on the uni server; being finalised)* |

So the **FPGA reports give area and timing, but not power.** FPGA power needs a separate PowerPlay run
(`quartus_pow`) with a switching-activity file (`.vcd`/`.saif`); that hasn't been run. The only measured **power**
number so far is the sky130 place-and-route estimate (125 mW).

---

## 1. ASIC — SkyWater sky130 (open-source)

### 1a. Synthesis (Yosys + ABC), cell area
Reports: `asic/sky130/out/*_area.rpt` (logs: `asic/sky130/out/*_yosys.log`, summaries `asic/sky130/out_*.txt`).
Timing reports (`*_timing.rpt`) are empty — the open synth script (`asic/sky130/synth.sh`) does synthesis only
(OpenSTA isn't installed locally); real timing comes from OpenROAD below.

| module | cells | cell area (µm²) | cell area (mm²) |
|---|---|---|---|
| `snn_core` (16+2 LIF neurons + W1 memory) | — | 393,195 | 0.39 |
| `snn_classifier` (parser + encoder + core) | — | 433,832 | 0.43 |
| **`snn_pkt_filter_asic`** (full chip, + 2 KiB buffer) | 69,330 | 1,148,869 | **1.15** |

Sequential share of the full chip: **29,166 flip-flops = 858,000 µm² ≈ 75 %** of the cell area
(`edfxtp_1` ×27,366 + `dfxtp_1` ×1,800). Most of that is the two flop-based memories (packet buffer + W1 weights);
multipliers: **0**.

### 1b. Place & route (OpenROAD via LibreLane) — area, timing, power
Full results on the GitHub release **`gds-snn_classifier`** (`report.md`, `metrics.json`). Block: `snn_classifier`.

| metric | value |
|---|---|
| die area | 1.28 mm² (1.13 × 1.14 mm) |
| std-cell area | 0.707 mm², 72,032 cells |
| **timing** | ≈ **99 MHz** typical (setup WNS −0.077 ns); ≈ 136 MHz fast corner; ≈ 51 MHz slow corner |
| **power** | **125 mW** @ 100 MHz, typical corner (vectorless estimate): 82.9 mW internal + 42.5 mW switching + ~0 leakage |
| DRC / LVS | 0 / 0 |
| multipliers | 0 |

---

## 2. FPGA — Cyclone V (Chameleon96, full HPS + SNN system)
Reports: `fpga/cv96_snn/output_files/led_blink_linux.fit.summary` (area), `*.sta.summary` (timing),
`*.fit.rpt` / `*.sta.rpt` (full). Tool: Quartus Prime 20.1 Lite.

### 2a. Area / resources (`.fit.summary`)
| resource | used | available | % |
|---|---|---|---|
| Logic (ALMs) | 2,378 | 41,910 | 6 % |
| Registers | 3,080 | — | — |
| Block memory bits | 9,776 | 5,662,720 | < 1 % |
| RAM blocks | 8 | 553 | 1 % |
| **DSP blocks** | **0** | 112 | **0 %** |
| I/O pins | 51 | 205 | 25 % |

(This is the whole system: the HPS interface + the SNN accelerator; the SNN alone is a small part.)

### 2b. Timing (`.sta.summary`, Slow 1100 mV 100 °C)
| clock | setup slack | hold slack |
|---|---|---|
| `h2f_user0_clk` (the SNN clock, 100 MHz) | **+0.975 ns** | +0.243 ns |
| HPS SDRAM write clock | +2.407 ns | +0.164 ns |

Positive slack everywhere → **meets 100 MHz**; the SNN clock's restricted Fmax is **110.8 MHz**.

### 2c. Power
**Not reported.** PowerPlay (`quartus_pow`) was not run, so there is no FPGA power number. To get one: run
`quartus_pow` with a `.vcd`/`.saif` from a gate-level sim.

---

## 3. FPGA — Cyclone V (in-line filter, standalone fit_check)
Report: `fpga/fit_check/output_files/snn_fw_fit.fit.summary`. This fits just the in-line filter (bigger 4 KiB buffer)
on its own, to size the datapath alone.

| resource | used | % |
|---|---|---|
| Logic (ALMs) | 5,871 | 14 % |
| Registers | 10,336 | — |
| RAM blocks | 14 | 3 % |
| DSP blocks | 0 | 0 % |

Standalone Fmax ≈ 111.6 MHz (from the STA report).

---

## 4. FPGA — Tang Nano 9K (Gowin GW1NR-9, open flow)
Report: `fpga/tang9k/nextpnr.log` (Yosys `synth_gowin` → nextpnr-himbaechel → gowin_pack).

| resource | used | available | % |
|---|---|---|---|
| LUT4 | 7,035 | 8,640 | 81 % |
| DFF | 2,657 | 6,480 | 41 % |
| BSRAM | 6 | 26 | 23 % |
| MUX2_LUT5 | 99 | 4,320 | 2 % |
| I/O | 12 | 276 | 4 % |
| **DSP** | **0** | — | — |

**Timing:** Max frequency **67.3 MHz** vs the 27 MHz board clock (2.5× margin). **Power:** no open-source power tool
for Gowin, so not reported.

---

## 5. Cadence 90 nm (Genus / Conformal / Innovus)
Run on the university server (`asic/README.md`, `asic/scripts/run_flow.sh`). Area, timing **and power** come out of
Genus (`report_area`, `report_timing`, `report_power` → `asic/out/<design>/syn_*/reports/`) and Innovus
(post-route). These reports are tracked in the repo once committed from the server — **being finalised**.

---

## 6. Summary across all targets

| target | flow | area | clock | power |
|---|---|---|---|---|
| sky130 | OpenROAD P&R | 1.28 mm² die, 72,032 cells | ≈ 99 MHz (tt) | 125 mW |
| sky130 | Yosys synth (full chip) | 1.15 mm², 69,330 cells | n/a | n/a |
| Cyclone V | Quartus (HPS + SNN) | 2,378 ALMs (6 %), 0 DSP | 110.8 MHz (meets 100) | not measured |
| Cyclone V | Quartus (filter only) | 5,871 ALMs (14 %), 0 DSP | 111.6 MHz | not measured |
| Tang Nano 9K | nextpnr | 7,035 LUT4 (81 %), 0 DSP | 67.3 MHz (uses 27) | not measured |
| Cadence 90 nm | Genus/Innovus | pending | 8 ns target | pending |

**Zero multipliers / DSP blocks on every FPGA target** — the point of using a spiking network.

---

## 7. Comparison with the literature

How these numbers sit against published SNN / in-network-ML hardware. Most prior SNN intrusion-detection work runs
*off* the data path (software or a neuromorphic chip fed by software); in-network ML (Taurus) uses *non-spiking*
models in a switch; generic FPGA SNN accelerators target images. Ours is an SNN fused into the NIC datapath, at line
rate, with no multipliers.

| work | platform | multipliers | area / power note | vs ours |
|---|---|---|---|---|
| Alom & Taha [C1] | TrueNorth chip | — | neuromorphic ASIC | SNN IDS 90.1 %, but off the data path (software feeds it) |
| Zhou & Li [C2] | software / sim | — | temporal (single-spike) coding | SNN IDS algorithm; no line-rate hardware |
| Taurus [C3] | switch ASIC | many | per-packet ML in-switch | non-spiking (DNN/SVM); not at the NIC→host boundary |
| Plagwitz et al. [J2] | FPGA | SNN: none | measures SNN vs CNN area & power | shows SNN beats CNN on power **only when sparse** — matches our event-driven, 0-DSP design |
| FPGA SNN accel. [C4] | FPGA | none | image benchmarks | not fused with a NIC |
| Na & Kim [J3] | ASIC | — | energy-efficient neuromorphic NoC | edge-AI processor, not packet-oriented |
| **Ours** | ASIC + FPGA NIC | **0** | **1.28 mm² / 125 mW (sky130); 6 % ALM, 0 DSP (FPGA)** | **SNN fused in the NIC datapath, line rate, 0 DSP** |

Our FPGA result (6 % of a Cyclone V, **0 DSP blocks**, 110 MHz) and the sky130 figures (1.28 mm², 125 mW) are
consistent with the literature's finding that SNNs win on hardware cost **when they are sparse and multiplier-free**
[J2]. Accuracy is still on synthetic data; published SNN-IDS on real data is ≈ 90 % [C1] (see `docs/training.md`).

### References

**Journal**
- **[J1]** Neftci, Mostafa, Zenke, "Surrogate Gradient Learning in Spiking Neural Networks," *IEEE Signal Processing Magazine*, 2019.
- **[J2]** Plagwitz, Hannig, Teich, Keszöcze, "To Spike or Not to Spike? A Quantitative Comparison of SNN and CNN FPGA Implementations," *ACM Trans. Embedded Computing Systems*, 2023.
- **[J3]** Na, Kim, "An Energy-Efficient Neuromorphic Processor Using Unified Refractory Control-Based NoC for Edge AI," *Electronics (MDPI)*, 2025.
- **[J4]** "Algorithm–hardware co-design of neuromorphic networks with dual memory pathways," *Nature Machine Intelligence*, 2026.

**Conference**
- **[C1]** Alom, Taha, "Network Intrusion Detection for Cyber Security on Neuromorphic Computing System," *IEEE IJCNN*, 2017.
- **[C2]** Zhou, Li, "Spiking Neural Networks with Single-Spike Temporal-Coded Neurons for Network Intrusion Detection," *IEEE ICPR*, 2020.
- **[C3]** Swamy et al., "Taurus: A Data Plane Architecture for Per-Packet ML," *ACM ASPLOS*, 2022.
- **[C4]** "Efficient Hardware Acceleration of Spiking Neural Networks using FPGA," *IEEE VTC2024-Spring*, 2024.

*Datasets:* Moustafa & Slay, UNSW-NB15 (MilCIS 2015); Sharafaldin et al., CIC-IDS2017 (ICISSP 2018).

---

*Report locations:* sky130 `asic/sky130/out/`; Cyclone V `fpga/cv96_snn/output_files/` and `fpga/fit_check/output_files/`;
Tang `fpga/tang9k/nextpnr.log`; sky130 P&R the `gds-snn_classifier` GitHub release; Cadence `asic/out/<design>/.../reports/`.
