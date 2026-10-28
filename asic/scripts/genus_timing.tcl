# ---------------------------------------------------------------------------
# Re-report timing on an ALREADY-synthesised Genus netlist, printing many more
# paths than the 10 that genus_core.tcl writes (report_timing -max_paths 10).
# It does NOT re-synthesise: it reads the variant's tech-mapped netlist + the
# 90 nm libs + that variant's SDC, then re-runs the timing engine.
#
# Per invocation it does ONE variant (set by TVARIANT, like the synthesis step
# does one variant per genus process). Writes into out/<DESIGN>/syn_<V>/reports/:
#   timing_setup_max<N>.rpt   the N worst setup paths          (N = MAXPATHS, default 100)
#   qor_timing.rpt            whole-design WNS / TNS / #violating-paths (report_qor)
#
# Run from asic/:
#   TVARIANT=optimal genus -no_gui -files scripts/genus_timing.tcl
#   (or let scripts/run_flow.sh timing loop over all three)
#   override the path count:  MAXPATHS=200 TVARIANT=fast genus -no_gui -files scripts/genus_timing.tcl
#
# NOTE: this is PRE-LAYOUT setup timing (wireload model), the same basis as
# synthesis. report_qor's "violating paths" count already covers the WHOLE
# design, so the 10-path cap in timing.rpt never hid violations - this script
# just gives fuller visibility of the near-critical paths. Real HOLD timing is
# only meaningful after CTS and is reported by scripts/innovus_signoff.tcl.
# ---------------------------------------------------------------------------
source scripts/setup.tcl

set VARIANT  [env_or TVARIANT optimal]
set MAXPATHS [env_or MAXPATHS 100]

if {![info exists PERIOD($VARIANT)]} { error "unknown TVARIANT '$VARIANT' (use fast|optimal|slow)" }
set NL  [tm_netlist $VARIANT]
set RPT [syn_dir $VARIANT]/reports
file mkdir $RPT
if {![file exists $NL]} {
    error "no netlist $NL - synthesise first:  genus -files scripts/genus_$VARIANT.tcl"
}
puts "==== Genus re-timing: $DESIGN, variant $VARIANT, period $PERIOD($VARIANT) ns, max_paths $MAXPATHS"

# ---- libraries + the already-mapped netlist (std cells resolve from the libs)
set_db init_lib_search_path $LIB_DIR
read_libs [file tail $SLOW_LIB]
read_hdl -v2001 $NL
elaborate $DESIGN

# ---- the same constraints this variant was synthesised with
read_sdc [tm_sdc $VARIANT]

# ---- the reports the user wants
report_timing -max_paths $MAXPATHS > $RPT/timing_setup_max${MAXPATHS}.rpt
report_qor                         > $RPT/qor_timing.rpt

puts "==== $VARIANT: wrote $RPT/timing_setup_max${MAXPATHS}.rpt and qor_timing.rpt"
puts "     (run  scripts/timing_summary.sh  to distil WNS/TNS/worst-path)"
if {$BATCH} { exit }
