# Innovus 1/7: import the tm_netlist_optimal + LEF + MMMC, connect power.
source scripts/innovus_setup.tcl
if {![file exists $NETLIST]} { error "$NETLIST missing: run genus_$PNR_VARIANT.tcl first" }

set ::env(SNN_SLOW_LIB)  $SLOW_LIB
set ::env(SNN_FAST_LIB)  $FAST_LIB
set ::env(SNN_SDC)       $SDC_FILE
set ::env(SNN_CAP_TABLE) $CAP_TABLE

set init_verilog              $NETLIST
set init_top_cell             $DESIGN
set init_lef_file             $TECH_LEF
set init_mmmc_file            scripts/mmmc.view
set init_design_netlisttype   Verilog
set init_pwr_net              $VDD_NET
set init_gnd_net              $VSS_NET

init_design
setDesignMode -process 90

globalNetConnect $VDD_NET -type pgpin -pin VDD  -inst *
globalNetConnect $VSS_NET -type pgpin -pin VSS  -inst *
globalNetConnect $VDD_NET -type pgpin -pin VPWR -inst *
globalNetConnect $VSS_NET -type pgpin -pin VGND -inst *
globalNetConnect $VDD_NET -type tiehi -inst *
globalNetConnect $VSS_NET -type tielo -inst *

checkDesign -netlist > $RPT_DIR/init_checkdesign.rpt
timeDesign -prePlace -outDir $RPT_DIR/init_timing
save_stage init
