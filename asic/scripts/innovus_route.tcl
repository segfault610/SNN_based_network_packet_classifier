# Innovus 6/7: detailed routing + post-route setup/hold optimisation (OCV).
source scripts/innovus_setup.tcl
setNanoRouteMode -routeWithTimingDriven true -routeWithSiDriven true
routeDesign -globalDetail
save_stage routed

setAnalysisMode -analysisType onChipVariation -cppr both
optDesign -postRoute       -outDir $RPT_DIR/postroute_opt
optDesign -postRoute -hold -outDir $RPT_DIR/postroute_opt_hold
save_stage postroute
