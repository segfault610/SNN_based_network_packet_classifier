# ---------------------------------------------------------------------------
# Genus synthesis body, shared by genus_fast.tcl / genus_optimal.tcl / genus_slow.tcl.
# Expects VARIANT to be set by the caller. Writes to out/<DESIGN>/syn_<VARIANT>/:
#   <DESIGN>_ti_netlist_<V>.vgenus   technology-independent (after syn_generic)
#   <DESIGN>_tm_netlist_<V>.v        technology-mapped + optimised (after syn_map/syn_opt)
#   <DESIGN>_<V>.sdc / .sdf          constraints for Innovus, delays for gate-level sim
#   <DESIGN>_genus_lec_<V>.do        Genus-generated Conformal dofile (alternative LEC)
#   reports/                         area, gates, timing, power, qor
# ---------------------------------------------------------------------------
source scripts/setup.tcl
set CLK_PERIOD $PERIOD($VARIANT)
lassign $EFFORT($VARIANT) GEN_EFF MAP_EFF OPT_EFF
set SYN  [syn_dir $VARIANT]
set RPT  $SYN/reports
file mkdir $RPT
# optional commands whose options differ between Genus releases: never abort the run
proc soft {script} {
    if {[catch {uplevel 1 $script} msg]} { puts "WARNING (non-fatal): $msg" }
}
puts "==== Genus: $DESIGN, variant $VARIANT, period $CLK_PERIOD ns, effort $GEN_EFF/$MAP_EFF/$OPT_EFF"

# ---- library + RTL
set_db init_lib_search_path $LIB_DIR
set_db init_hdl_search_path $RTL_DIR
read_libs [file tail $SLOW_LIB]
read_hdl -v2001 $RTL_FILES
elaborate $DESIGN
check_design -unresolved          > $RPT/check_design.rpt

# ---- constraints: constraints/snn.sdc with this variant's clock period
set fi [open constraints/snn.sdc r]; set sdc [read $fi]; close $fi
regsub {set CLK_PERIOD [0-9.]+} $sdc "set CLK_PERIOD $CLK_PERIOD" sdc
set SDC_IN $SYN/${DESIGN}_${VARIANT}_in.sdc
set fo [open $SDC_IN w]; puts $fo $sdc; close $fo
read_sdc $SDC_IN
soft { report_timing -lint           > $RPT/timing_lint.rpt }

# ---- synthesis
set_db syn_generic_effort $GEN_EFF
set_db syn_map_effort     $MAP_EFF
set_db syn_opt_effort     $OPT_EFF

syn_generic
write_hdl > $SYN/${DESIGN}_ti_netlist_${VARIANT}.vgenus

syn_map
syn_opt
if {$VARIANT ne "slow"} { syn_opt -incremental }

# ---- outputs
write_hdl > [tm_netlist $VARIANT]
write_sdc > [tm_sdc $VARIANT]
soft { write_sdf -timescale ns -nonegchecks -recrem split -edges check_edge \
          > $SYN/${DESIGN}_tm_netlist_${VARIANT}.sdf }
soft { write_do_lec -golden_design rtl -revised_design [tm_netlist $VARIANT] \
          -logfile $SYN/${DESIGN}_genus_lec_${VARIANT}.log > $SYN/${DESIGN}_genus_lec_${VARIANT}.do }

# ---- reports
report_area                       > $RPT/area.rpt
soft { report_area -depth 3          > $RPT/area_hier.rpt }
report_gates                      > $RPT/gates.rpt
report_timing -max_paths 10       > $RPT/timing.rpt        ;# worst constrained (clocked) paths
# with this attribute report_timing lists only UNconstrained paths; expected: "No unconstrained paths found"
set_db timing_report_unconstrained true
report_timing                     > $RPT/timing_unconstrained.rpt
set_db timing_report_unconstrained false
report_power                      > $RPT/power.rpt
report_qor                        > $RPT/qor.rpt
soft { report_messages               > $RPT/messages.rpt }
set fo [open $RPT/variant.txt w]
puts $fo "variant $VARIANT  period_ns $CLK_PERIOD  effort $GEN_EFF/$MAP_EFF/$OPT_EFF"
close $fo

puts "==== Genus $VARIANT done -> [tm_netlist $VARIANT]"
if {$BATCH} { exit }
