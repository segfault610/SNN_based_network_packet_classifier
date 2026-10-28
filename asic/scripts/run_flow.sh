#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Batch driver for the Cadence flow (uni server). Every step is a Tcl script in
# this folder; this file only calls them in order. Run from anywhere:
#
#   scripts/run_flow.sh sim-rtl       xrun: RTL functional verification (T1..T10)
#   scripts/run_flow.sh syn           Genus fast + optimal + slow, then genus_summary
#   scripts/run_flow.sh syn-optimal   Genus one variant (syn-fast / syn-slow likewise)
#   scripts/run_flow.sh timing        Genus re-report timing (max_paths 100) all 3 + summary
#   scripts/run_flow.sh timing-summary  distil existing reports -> timing_summary.txt (no tools)
#   scripts/run_flow.sh schematic     open the full design in the Genus GUI schematic viewer (needs X)
#   scripts/run_flow.sh lec           Conformal RTL vs tm_netlist_{fast,optimal,slow}
#   scripts/run_flow.sh lec-genus     Conformal with the Genus-written dofile (recommended first)
#   scripts/run_flow.sh sim-gls       xrun: tm_netlist_optimal, zero delay
#   scripts/run_flow.sh pnr           Innovus on tm_netlist_optimal (all stages)
#   scripts/run_flow.sh lec-pnr       Conformal tm_netlist_optimal vs routed netlist
#   scripts/run_flow.sh sim-sdf       xrun: routed netlist + post-route SDF
#   scripts/run_flow.sh all           everything above, in that order
#
# Environment: DESIGN (snn_pkt_filter_asic), GPDK090 (PDK dig/ dir), CELL_V (gsclib090 Verilog models),
#              CLK_FAST/CLK_OPTIMAL/CLK_SLOW, PNR_VARIANT, CAP_TABLE, GDS_MAP
# ---------------------------------------------------------------------------
set -e
cd "$(dirname "$0")/.."                          # asic/
export BATCH=1
DESIGN=${DESIGN:-snn_pkt_filter_asic}; export DESIGN
PDK=${GPDK090:-/home/cadence/install/FOUNDRY/digital/90nm/dig}
OUT=out/$DESIGN
VEC=$(cd ../sim/vectors && pwd)
mkdir -p $OUT/sim

cell_models() {
  if [ -z "$CELL_V" ]; then
    CELL_V=$(ls $PDK/vlog/*.v $PDK/verilog/*.v 2>/dev/null | head -1)
  fi
  [ -f "$CELL_V" ] || { echo "set CELL_V=<gsclib090 cell Verilog>  (try: find $PDK -name '*.v')"; exit 1; }
}
xr() {   # xr <log-name> <args...>
  local name=$1; shift
  xrun -F scripts/${XRUN_F} -input scripts/xrun_batch.tcl +VEC_DIR=$VEC \
       -xmlibdirname $OUT/sim/xcelium_$name.d -l $OUT/sim/xrun_$name.log "$@"
  grep -E "RESULT" $OUT/sim/xrun_$name.log
}

step() {
  case $1 in
    sim-rtl)     XRUN_F=xrun_rtl.f xr rtl ;;
    syn-fast|syn-optimal|syn-slow)
                 v=${1#syn-}; mkdir -p $OUT/syn_$v
                 genus -no_gui -log $OUT/syn_$v/genus_$v -files scripts/genus_$v.tcl ;;
    syn)         step syn-fast; step syn-optimal; step syn-slow; tclsh scripts/genus_summary.tcl ;;
    timing-fast|timing-optimal|timing-slow)
                 v=${1#timing-}
                 TVARIANT=$v MAXPATHS=${MAXPATHS:-100} \
                   genus -no_gui -log $OUT/syn_$v/genus_timing_$v -files scripts/genus_timing.tcl ;;
    timing)      step timing-fast; step timing-optimal; step timing-slow; scripts/timing_summary.sh ;;
    timing-summary) scripts/timing_summary.sh ;;      # distil existing reports, no tools needed
    schematic)   genus -files scripts/genus_schematic.tcl ;;  # GUI schematic (needs X; SYNTH=1 for gate-level)
    lec-fast|lec-optimal|lec-slow)
                 mkdir -p $OUT/lec
                 lec -xl -nogui -tclmode -dofile scripts/${1/-/_}.tcl
                 grep -iE "non-equivalent|equivalent|abort" $OUT/lec/${1/-/_}.log | tail -6 ;;
    lec)         step lec-fast; step lec-optimal; step lec-slow ;;
    lec-genus)   # Genus-written composite dofile: RTL -> fv_map -> tm_netlist, with Genus's own mapping hints
                 v=${PNR_VARIANT:-optimal}
                 lec -xl -nogui -dofile $OUT/syn_$v/${DESIGN}_genus_lec_$v.do | tee $OUT/lec/lec_genus_$v.log | tail -30 ;;
    sim-gls)     cell_models
                 XRUN_F=xrun_gls.f xr gls_${PNR_VARIANT:-optimal} -v $CELL_V \
                   $OUT/syn_${PNR_VARIANT:-optimal}/${DESIGN}_tm_netlist_${PNR_VARIANT:-optimal}.v \
                   -nospecify -notimingchecks ;;
    pnr)         mkdir -p $OUT/pnr
                 innovus -no_gui -log $OUT/pnr/innovus.log -files scripts/innovus_all.tcl ;;
    lec-pnr)     lec -xl -nogui -tclmode -dofile scripts/lec_pnr.tcl
                 grep -iE "non-equivalent|equivalent|abort" $OUT/lec/lec_pnr.log | tail -6 ;;
    sim-sdf)     cell_models
                 XRUN_F=xrun_gls.f xr sdf -v $CELL_V $OUT/pnr/${DESIGN}_pnr_netlist.v \
                   -define SDF_FILE=\"$PWD/$OUT/pnr/${DESIGN}_pnr.sdf\" -sdf_verbose ;;
    all)         for s in sim-rtl syn lec sim-gls pnr lec-pnr sim-sdf; do echo "######## $s"; step $s; done ;;
    *)           sed -n '2,23p' "$0"; exit 1 ;;
  esac
}
step "${1:-help}"
