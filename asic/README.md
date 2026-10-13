# ASIC flow (Cadence: Xcelium, Genus, Conformal, Innovus, gsclib090 90 nm)

Run everything **from `asic/`**. Every step is a separate Tcl file in `scripts/`.
`scripts/run_flow.sh` just calls them in order, in batch mode.

Top: `snn_pkt_filter_asic` (the full in-line firewall: 2 KiB packet buffer, parser,
encoder, SNN). Use `DESIGN=snn_core` or `DESIGN=snn_classifier` to synthesise only part of it.

## Commands

| step | interactive (tool prompt) | batch |
|---|---|---|
| RTL functional sim | `xrun -F scripts/xrun_rtl.f -input scripts/xrun_batch.tcl +VEC_DIR=$PWD/../sim/vectors` (waves: `-input scripts/xrun_waves.tcl`, then `simvision waves.shm`) | `scripts/run_flow.sh sim-rtl` |
| Genus fast (5 ns) | `genus -files scripts/genus_fast.tcl` | `scripts/run_flow.sh syn-fast` |
| Genus optimal (8 ns) | `genus -files scripts/genus_optimal.tcl` | `scripts/run_flow.sh syn-optimal` |
| Genus slow (12 ns) | `genus -files scripts/genus_slow.tcl` | `scripts/run_flow.sh syn-slow` |
| compare variants, publish main netlist | `tclsh scripts/genus_summary.tcl` | (part of `run_flow.sh syn`) |
| LEC RTL vs each netlist | `lec -xl -nogui -tclmode -dofile scripts/lec_optimal.tcl` (and `_fast`, `_slow`) | `scripts/run_flow.sh lec` |
| gate-level sim, zero delay | see `run_flow.sh sim-gls` (needs `CELL_V`=gsclib090 Verilog models) | `CELL_V=... scripts/run_flow.sh sim-gls` |
| Innovus, all stages | `innovus -files scripts/innovus_all.tcl` | `scripts/run_flow.sh pnr` |
| Innovus, one stage | `source out/<D>/pnr/<D>_prects.enc` then `source scripts/innovus_cts.tcl` | |
| LEC netlist vs routed | `lec -xl -nogui -tclmode -dofile scripts/lec_pnr.tcl` | `scripts/run_flow.sh lec-pnr` |
| post-route sim with SDF | | `CELL_V=... scripts/run_flow.sh sim-sdf` |
| everything | | `CELL_V=... scripts/run_flow.sh all` |

## Before the first run on the uni server

1. **Cell models for gate-level sim.** `sim-gls`, `sim-sdf` and `all` need the gsclib090 Verilog models.
   The path is a guess until you check it:
   `find /home/cadence/install/FOUNDRY/digital/90nm/dig -name "*.v"`, then `export CELL_V=<that file>`.
2. **PDK path variable is `GPDK090`, not `PDK`.** The default is `/home/cadence/install/FOUNDRY/digital/90nm/dig`.
   If the server keeps it elsewhere, `export GPDK090=<.../dig>`. A generic `PDK` variable (on the laptop it points
   at sky130) is deliberately ignored, so it can't silently load the wrong library.
3. **Run from `asic/`.** Every script checks that `../rtl` exists and stops otherwise.
4. **First run: watch each tool's log.** The scripts were dry-run with stubbed tool commands (Tcl syntax, paths, step
   order) but never under real Genus/Conformal/Innovus. Option names that differ between tool releases show up
   in the first lines of the log. The optional Genus commands (`write_sdf`, `write_do_lec`, `report_area -depth`)
   are wrapped so they only warn.
5. **Expect a large design.** About 29 k flip-flops: 18.4 k in the flop-based 2 KiB packet buffer, 8.2 k in the
   64×128-bit W1 weight memory, about 2.5 k elsewhere. Genus/Innovus runtimes are therefore minutes to tens of
   minutes, not seconds. `DESIGN=snn_core` is a much smaller first try.
6. **Old script names still work.** `genus_syn.tcl`, `lec.tcl` and `innovus_pnr.tcl` now forward to
   `genus_optimal.tcl`, `lec_optimal.tcl` and `innovus_all.tcl`.
7. **Git push from the laptop.** The `origin` remote is HTTPS, which needs a token. SSH works with the existing key:
   `git push git@github.com:segfault610/SNN_based_network_packet_classifier.git main`.

## Scripts

| file | what |
|---|---|
| `setup.tcl` | shared paths, design name, clock period and effort of each variant, output names |
| `genus_core.tcl` | synthesis body: read, elaborate, constrain, `syn_generic`, `syn_map`, `syn_opt`, write, report |
| `genus_fast.tcl` / `genus_optimal.tcl` / `genus_slow.tcl` | set `VARIANT`, source `genus_core.tcl` |
| `genus_summary.tcl` | slack/area/power of all three into `qor_summary.txt`; copies the optimal netlist to `out/<D>/<D>_tm_netlist.v` |
| `lec_core.tcl`, `lec_{fast,optimal,slow}.tcl` | Conformal (Tcl mode) RTL vs `tm_netlist_<variant>` |
| `lec_pnr.tcl` | Conformal `tm_netlist_optimal` vs the Innovus netlist |
| `mmmc.view` | setup at `slow.lib`, hold at `fast.lib` |
| `innovus_setup.tcl` | PD settings: netlist = `tm_netlist_optimal`, utilisation 0.6, power layers M7/M8 |
| `innovus_init` → `floorplan` → `powerplan` → `place` → `cts` → `route` → `signoff` | one file per stage, each ends with `saveDesign` |
| `innovus_all.tcl` | sources the seven stages in order |
| `xrun_rtl.f`, `xrun_gls.f`, `xrun_batch.tcl`, `xrun_waves.tcl` | Xcelium file lists and run scripts |
| `run_flow.sh` | batch driver |
| `genus_syn.tcl`, `lec.tcl`, `innovus_pnr.tcl` | old names, now point to the optimal variant / `innovus_all.tcl` |

## Variants

| variant | clock | effort (generic/map/opt) | purpose |
|---|---|---|---|
| fast | 5 ns, 200 MHz | high/high/high + incremental opt | how far the design can be pushed; may show negative slack |
| **optimal** | **8 ns, 125 MHz** | medium/high/high + incremental opt | the requirement (1 GbE GMII byte clock). **This netlist goes to PD** |
| slow | 12 ns, 83 MHz | low/low/low | relaxed timing: smallest area and power, fastest run |

Override with `CLK_FAST`, `CLK_OPTIMAL`, `CLK_SLOW`. Use `PNR_VARIANT=fast` to place and route another variant.

## Outputs (`out/<DESIGN>/`)

```
syn_<v>/<D>_ti_netlist_<v>.vgenus   after syn_generic (technology independent)
syn_<v>/<D>_tm_netlist_<v>.v        after syn_map + syn_opt (technology mapped)  <- LEC, GLS, Innovus
syn_<v>/<D>_<v>.sdc / .sdf          constraints for Innovus / delays for GLS
syn_<v>/<D>_genus_lec_<v>.do        Genus-written LEC dofile (fallback: lec -xl -nogui -dofile <it>)
syn_<v>/reports/                    area, area_hier, gates, timing, power, qor
qor_summary.txt                     the three variants side by side
<D>_tm_netlist.v / .sdc             main netlist (= optimal)
lec/lec_<v>.log, lec/lec_pnr.log
pnr/<D>_<stage>.enc                 restore points
pnr/reports/                        per-stage timing, congestion, clock, DRC, connectivity, area, power
pnr/<D>_pnr_netlist.v, <D>_pnr.sdf, <D>_routed.def  (<D>.gds if GDS_MAP is set)
sim/xrun_<run>.log
```

## What to expect

- **xrun:** `RESULT: PASS (10 tests)` for RTL, gate-level and SDF runs. See `docs/functional_verification.md`.
- **LEC:** every compare point equivalent, with 0 non-equivalent and 0 aborted. If Genus merged flops and points stay
  unmapped, run the Genus-written dofile (`syn_optimal/<D>_genus_lec_optimal.do`) instead.
- **Area:** about 29 k flip-flops in total:
  - 18.4 k in the flop-based 2 KiB packet buffer;
  - 8.2 k in the 64×128-bit W1 weight memory;
  - the remaining ~2.5 k across the rest of the design.

  For comparison, the same RTL is 1.15 mm² in sky130 (`asic/sky130`); 90 nm is smaller. Replacing both memories
  with SRAM macros is the main area win before tape-out.
- **Untested:** the scripts have been dry-run with stubbed tools, so the Tcl, paths and order are checked, but they have
  not run under real Cadence tools here (none on this laptop). Check the first log of each tool for option errors.

## Open-source flow (SkyWater sky130, on the laptop)

| step | status |
|---|---|
| Yosys + ABC synthesis of the full top `snn_pkt_filter_asic` onto `sky130_fd_sc_hd` (`asic/sky130/synth.sh snn_pkt_filter_asic`) | **done**: 69,316 cells, 1.15 mm² cell area. 0.82 mm² of that is 27,366 enable flip-flops (packet buffer + W1) |
| Gate-level simulation of that netlist with the sky130 cell models (`sim/run_asic.sh gl`) | **done**: T1–T10 pass |
| Static timing (OpenSTA) | not done (not installed). The current numbers are area only |
| Floorplan / place / CTS / route / DRC / LVS / GDS (OpenROAD via LibreLane, ex-OpenLane 2) | **not done yet**. The PDK here already has `libs.tech/librelane`, and Docker works, so it can run locally |
