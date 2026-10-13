# Innovus 5/7: clock tree synthesis (CCOpt) + post-CTS setup and hold optimisation.
source scripts/innovus_setup.tcl
create_ccopt_clock_tree_spec -file $PNR_DIR/${DESIGN}_ccopt.spec
source $PNR_DIR/${DESIGN}_ccopt.spec
ccopt_design -cts

report_timing                      > $RPT_DIR/postcts_timing.rpt
report_clock_timing -type latency  > $RPT_DIR/postcts_clock_latency.rpt
report_clock_timing -type skew     > $RPT_DIR/postcts_clock_skew.rpt
report_ccopt_skew_groups           > $RPT_DIR/postcts_skew_groups.rpt
reportCongestion -overflow         > $RPT_DIR/postcts_congestion.rpt
save_stage cts

optDesign -postCTS       -outDir $RPT_DIR/postcts_opt
optDesign -postCTS -hold -outDir $RPT_DIR/postcts_opt_hold
report_timing            > $RPT_DIR/postcts_opt_timing.rpt
report_timing -early     > $RPT_DIR/postcts_opt_hold_timing.rpt
save_stage postcts
