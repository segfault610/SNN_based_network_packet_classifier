# ---------------------------------------------------------------------------
# Conformal LEC (Tcl mode): RTL (golden) vs Genus tm_netlist_<VARIANT> (revised).
# Shared by lec_fast.tcl / lec_optimal.tcl / lec_slow.tcl, which set VARIANT.
# Log: out/<DESIGN>/lec/lec_<VARIANT>.log . Expected: all compare points EQUIVALENT,
# no non-equivalent / aborted points.
# ---------------------------------------------------------------------------
source scripts/setup.tcl
set LEC_DIR $OUT/lec
file mkdir $LEC_DIR
set REVISED [tm_netlist $VARIANT]
if {![file exists $REVISED]} { error "$REVISED missing: run genus_$VARIANT.tcl first" }

set_log_file $LEC_DIR/lec_$VARIANT.log -replace

# 1. library
read_library $SLOW_LIB -liberty -both

# 2. golden = RTL, 3. revised = technology-mapped netlist
eval read_design $RTL_PATHS -verilog2k -golden   ;# eval: one argument per file
read_design $REVISED   -verilog   -revised

# 4. root module on both sides
set_root_module $DESIGN -golden
set_root_module $DESIGN -revised

# Genus removes constant / unloaded flops (e.g. the always-0 tuser output register)
set_flatten_model -seq_constant
set_flatten_model -gated_clock
set_analyze_option -auto

# 5. LEC mode, 6. map + compare
set_system_mode lec
report_unmapped_points -summary
add_compared_points -all
compare

# 7. results
report_verification
report_statistics
report_compare_data -class nonequivalent
report_compare_data -class abort

puts "==== LEC $VARIANT done, see $LEC_DIR/lec_$VARIANT.log"
if {$BATCH} { exit -force }
