# Innovus place & route (floorplan -> power -> place -> CTS -> route).
# Run from asic/ after Genus:  DESIGN=snn_core innovus -no_gui -files scripts/innovus_pnr.tcl
if {[info exists ::env(DESIGN)]} { set DESIGN $::env(DESIGN) } else { set DESIGN snn_pkt_filter_asic }
set OUT          out/$DESIGN
set ::env(SDC)   $OUT/${DESIGN}.sdc
set OUT_DIR      $OUT/pnr_reports
file mkdir $OUT_DIR

set TECH_LEF     "/home/cadence/install/FOUNDRY/digital/90nm/dig/lef/gsclib090_translated.lef"
set VDD_NET      VDD
set VSS_NET      VSS

set init_verilog              $OUT/${DESIGN}_netlist.v
set init_top_cell             $DESIGN
set init_lef_file             $TECH_LEF
set init_mmmc_file            scripts/mmmc.view
set init_design_netlisttype   Verilog
set init_pwr_net              $VDD_NET
set init_gnd_net              $VSS_NET

init_design

globalNetConnect $VDD_NET -type pgpin -pin VDD -inst *
globalNetConnect $VSS_NET -type pgpin -pin VSS -inst *

globalNetConnect $VDD_NET -type pgpin -pin VPWR -inst *
globalNetConnect $VSS_NET -type pgpin -pin VGND -inst *

floorPlan -r 1.0 0.60 10 10 10 10

checkDesign -floorplan

saveDesign $OUT/${DESIGN}_floorplan.enc

addRing \
    -nets "$VDD_NET $VSS_NET" \
    -type core_rings \
    -follow core \
    -layer {top M8 bottom M8 left M7 right M7} \
    -width 2 \
    -spacing 2 \
    -offset 2

addStripe \
    -nets "$VDD_NET $VSS_NET" \
    -direction vertical \
    -layer M7 \
    -width 1 \
    -spacing 1 \
    -set_to_set_distance 40 \
    -start_from left

addStripe \
    -nets "$VDD_NET $VSS_NET" \
    -direction horizontal \
    -layer M8 \
    -width 1 \
    -spacing 1 \
    -set_to_set_distance 40 \
    -start_from bottom

sroute \
    -nets "$VDD_NET $VSS_NET" \
    -connect {corePin blockPin padPin floatingStripe} \
    -layerChangeRange {M1 M8} \
    -allowJogging true \
    -allowLayerChange true

verifyConnectivity \
    -type special \
    -nets "$VDD_NET $VSS_NET"

checkDesign -all

saveDesign $OUT/${DESIGN}_powerplan.enc

defOut -floorplan $OUT/${DESIGN}_floorplan.def



verifyConnectivity \
    -type special \
    -nets {VDD VSS} \
    > $OUT_DIR/preplace_pg_connectivity.rpt

checkDesign -all \
    > $OUT_DIR/preplace_checkdesign.rpt

setPlaceMode -fp false

placeDesign -noPrePlaceOpt

checkPlace \
    > $OUT_DIR/placement_check.rpt

reportCongestion -overflow \
    > $OUT_DIR/placement_congestion.rpt

report_timing \
    > $OUT_DIR/prects_timing.rpt

report_area \
    > $OUT_DIR/placement_area.rpt

saveDesign $OUT/${DESIGN}_placement.enc

optDesign -preCTS

report_timing \
    > $OUT_DIR/prects_opt_timing.rpt

reportCongestion -overflow \
    > $OUT_DIR/prects_opt_congestion.rpt

saveDesign $OUT/${DESIGN}_prects.enc

create_ccopt_clock_tree_spec \
    -file $OUT/${DESIGN}_ccopt.spec

source $OUT/${DESIGN}_ccopt.spec

ccopt_design -cts

report_timing \
    > $OUT_DIR/postcts_timing.rpt

report_clock_timing \
    -type latency \
    > $OUT_DIR/postcts_clock_latency.rpt

report_ccopt_skew_groups \
    > $OUT_DIR/postcts_skew.rpt

reportCongestion -overflow \
    > $OUT_DIR/postcts_congestion.rpt

saveDesign $OUT/${DESIGN}_cts.enc

optDesign -postCTS

report_timing \
    > $OUT_DIR/postcts_opt_timing.rpt

saveDesign $OUT/${DESIGN}_postcts.enc

routeDesign -globalDetail

saveDesign $OUT/${DESIGN}_routed.enc

reportCongestion -overflow \
    > $OUT_DIR/postroute_congestion.rpt

report_timing \
    > $OUT_DIR/postroute_timing.rpt

report_timing \
    -early \
    > $OUT_DIR/postroute_hold_timing.rpt

report_clock_timing \
    -type latency \
    > $OUT_DIR/postroute_clock_latency.rpt

verify_drc \
    -report $OUT_DIR/postroute_drc.rpt

verifyConnectivity \
    -type all \
    -nets {VDD VSS} \
    > $OUT_DIR/postroute_pg_connectivity.rpt

checkPlace \
    > $OUT_DIR/postroute_checkplace.rpt

checkDesign -all \
    > $OUT_DIR/postroute_checkdesign.rpt

report_area \
    > $OUT_DIR/postroute_area.rpt

report_power \
    > $OUT_DIR/postroute_power.rpt

defOut -floorplan \
    $OUT/${DESIGN}_routed.def

saveDesign $OUT/${DESIGN}_final.enc

