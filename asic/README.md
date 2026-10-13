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

To find the cell models: `find /home/cadence/install/FOUNDRY/digital/90nm/dig -name "*.v"`.
If the PDK lives elsewhere, set `GPDK090=<.../dig>`.

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
