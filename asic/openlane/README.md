# sky130 RTL → GDS (LibreLane on GitHub Actions)

The open-source flow runs **only in GitHub Actions** (`.github/workflows/sky130_gds.yml`), nothing on the laptop.
It works like the Tiny Tapeout GDS action, but for this project's own blocks (Tiny Tapeout's tile size and
fixed pinout are far too small for them).

| block | config | when it runs |
|---|---|---|
| `snn_classifier`: parser + encoder + SNN behind the config bus, ~150 pins | `snn_classifier/config.yaml` | every push to `main` that touches `rtl/` or `asic/openlane/` |
| `snn_pkt_filter_asic`: the full in-line firewall with its 2 KiB buffer | `snn_pkt_filter_asic/config.yaml` | on demand: GitHub → Actions → **sky130 GDS** → Run workflow → pick the design |

**Flow:** LibreLane 3.0.14 (pinned), sky130A, `sky130_fd_sc_hd` cells. It runs Verilator lint, Yosys, OpenROAD
(floorplan, power grid, placement, clock tree, routing, timing repair), multi-corner STA, Magic + KLayout DRC,
Netgen LVS and the GDS stream-out. The clock is 10 ns (100 MHz): sky130 is slower than the uni's 90 nm library.

**Results** of each run:
- the job summary (table of area, timing, power, DRC, LVS);
- the run's artifact: report, metrics, logs, GDS, DEF, SDF, step reports;
- the public release **`gds-<design>`** on the repo's Releases page. Its notes hold the report, and its assets
  are `report.md`, `metrics.json`, `<design>_layout.png`, `<design>.gds.gz`, the netlist, `flow.log` and
  `error_summary.txt`. Each run replaces them.

**Run time on a GitHub runner (4 cores):** roughly 30–60 min for `snn_classifier` and 2–5 h for the full chip
(job limit 6 h). The full chip's memories are built from flip-flops, so routing is the slow part.

**Files:** `render_gds.py` (KLayout: GDS → PNG), `summarize.py` (metrics → Markdown + GitHub annotation).
