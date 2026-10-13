# ---------------------------------------------------------------------------
# Conformal LEC (Tcl mode): synthesis netlist (golden) vs Innovus netlist (revised).
# Proves place & route (CTS buffers, sizing, hold fixing, tie cells) kept the logic.
#   from asic/ after innovus_all.tcl:   lec -xl -nogui -tclmode -dofile scripts/lec_pnr.tcl
# ---------------------------------------------------------------------------
source scripts/setup.tcl
set LEC_DIR $OUT/lec
file mkdir $LEC_DIR
set GOLDEN [tm_netlist $PNR_VARIANT]
if {![file exists $PNR_NETLIST]} { error "$PNR_NETLIST missing: run innovus_all.tcl first" }

set_log_file $LEC_DIR/lec_pnr.log -replace
read_library $SLOW_LIB -liberty -both
read_design $GOLDEN      -verilog -golden
read_design $PNR_NETLIST -verilog -revised
set_root_module $DESIGN -golden
set_root_module $DESIGN -revised
set_flatten_model -seq_constant
set_analyze_option -auto
set_system_mode lec
add_compared_points -all
compare
report_verification
report_statistics
report_compare_data -class nonequivalent

puts "==== LEC tm_netlist_$PNR_VARIANT vs pnr netlist done, see $LEC_DIR/lec_pnr.log"
if {$BATCH} { exit -force }
