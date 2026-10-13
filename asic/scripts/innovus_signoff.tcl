# Innovus 7/7: fillers, verification, final reports, outputs for LEC / gate-level sim.
source scripts/innovus_setup.tcl
set fill [existing_cells $FILLER_CELLS]
if {[llength $fill]} { addFiller -cell $fill -prefix FILLER }

# ---- checks (all should be clean)
verify_drc -report $RPT_DIR/signoff_drc.rpt
verifyConnectivity -type all -report $RPT_DIR/signoff_connectivity.rpt
verifyConnectivity -type special -nets "$VDD_NET $VSS_NET" > $RPT_DIR/signoff_pg_connectivity.rpt
verifyProcessAntenna -report $RPT_DIR/signoff_antenna.rpt
checkPlace     > $RPT_DIR/signoff_checkplace.rpt
checkDesign -all > $RPT_DIR/signoff_checkdesign.rpt

# ---- timing / area / power
timeDesign -postRoute       -outDir $RPT_DIR/signoff_timing
timeDesign -postRoute -hold -outDir $RPT_DIR/signoff_timing_hold
report_timing                       > $RPT_DIR/signoff_setup.rpt
report_timing -early                > $RPT_DIR/signoff_hold.rpt
report_clock_timing -type latency   > $RPT_DIR/signoff_clock_latency.rpt
report_clock_timing -type skew      > $RPT_DIR/signoff_clock_skew.rpt
reportCongestion -overflow          > $RPT_DIR/signoff_congestion.rpt
report_area                         > $RPT_DIR/signoff_area.rpt
report_power                        > $RPT_DIR/signoff_power.rpt
summaryReport -noHtml -outfile $RPT_DIR/signoff_summary.rpt

# ---- outputs
saveNetlist $PNR_NETLIST                              ;# -> lec_pnr.tcl, xrun sim-sdf
write_sdf $PNR_SDF                                               ;# post-route delays for gate-level sim
defOut -floorplan -netlist -routing $PNR_DIR/${DESIGN}_routed.def
if {[info exists ::env(GDS_MAP)]} {
    streamOut $PNR_DIR/${DESIGN}.gds -mapFile $::env(GDS_MAP) -units 1000 -mode ALL
}
save_stage final
