# Innovus 2/7: floorplan (core area from utilisation; IO pins are placed by placeDesign).
source scripts/innovus_setup.tcl
floorPlan -r $FP_ASPECT $FP_UTIL $FP_MARGIN $FP_MARGIN $FP_MARGIN $FP_MARGIN
checkDesign -floorplan > $RPT_DIR/floorplan_checkdesign.rpt
save_stage floorplan
