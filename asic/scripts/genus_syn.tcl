# Genus synthesis.  Run from asic/:   DESIGN=snn_core genus -files scripts/genus_syn.tcl
#   DESIGN = snn_core | snn_classifier (parser+encoder+SNN) | snn_pkt_filter_asic (full in-line firewall)
if {[info exists ::env(DESIGN)]} { set DESIGN $::env(DESIGN) } else { set DESIGN snn_pkt_filter_asic }
set RTL ../rtl
set OUT out/$DESIGN
file mkdir $OUT

set_db init_lib_search_path /home/cadence/install/FOUNDRY/digital/90nm/dig/lib/
read_libs slow.lib

set_db init_hdl_search_path $RTL
read_hdl -v2001 {sync_fifo.v pkt_parser.v spike_encoder.v snn_core.v snn_classifier.v snn_pkt_filter.v snn_pkt_filter_asic.v snn_lookaside_avmm.v}
elaborate $DESIGN
check_design -unresolved

read_sdc constraints/snn.sdc

set_db syn_generic_effort medium
set_db syn_map_effort     medium
set_db syn_opt_effort     medium

syn_generic
syn_map
syn_opt

write_hdl            > $OUT/${DESIGN}_netlist.v
write_sdc            > $OUT/${DESIGN}.sdc
write_do_lec -golden_design rtl -revised_design $OUT/${DESIGN}_netlist.v > $OUT/${DESIGN}_genus_lec.do

report_area          > $OUT/${DESIGN}_area.rpt
report_area -depth 3 > $OUT/${DESIGN}_area_hier.rpt
report_gates         > $OUT/${DESIGN}_gates.rpt
report_power         > $OUT/${DESIGN}_power.rpt
report_timing -nworst 5 > $OUT/${DESIGN}_timing.rpt
report_qor           > $OUT/${DESIGN}_qor.rpt
puts "Synthesis of $DESIGN done -> $OUT"
