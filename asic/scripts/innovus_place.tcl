# Innovus 4/7: placement + pre-CTS optimisation.
source scripts/innovus_setup.tcl
setPlaceMode -fp false -place_global_place_io_pins true
placeDesign -noPrePlaceOpt
set ties [existing_cells $TIE_CELLS]
if {[llength $ties]} { setTieHiLoMode -cell $ties -maxFanout 8; addTieHiLo -prefix LTIE }

checkPlace                > $RPT_DIR/place_checkplace.rpt
reportCongestion -overflow > $RPT_DIR/place_congestion.rpt
report_timing             > $RPT_DIR/place_timing.rpt
report_area               > $RPT_DIR/place_area.rpt
save_stage placement

optDesign -preCTS -outDir $RPT_DIR/prects_opt
report_timing             > $RPT_DIR/prects_opt_timing.rpt
reportCongestion -overflow > $RPT_DIR/prects_opt_congestion.rpt
save_stage prects
