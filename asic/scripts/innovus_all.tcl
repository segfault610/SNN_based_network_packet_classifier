# ---------------------------------------------------------------------------
# Full Innovus flow on tm_netlist_optimal.
#   from asic/:   innovus -no_gui -files scripts/innovus_all.tcl
# Each stage saves out/<DESIGN>/pnr/<DESIGN>_<stage>.enc. To resume or debug:
#   innovus  ->  source out/<DESIGN>/pnr/<DESIGN>_prects.enc  ->  source scripts/innovus_cts.tcl ...
# ---------------------------------------------------------------------------
foreach stage {init floorplan powerplan place cts route signoff} {
    puts "==================== Innovus stage: $stage"
    source scripts/innovus_$stage.tcl
}
puts "==== Innovus done: [file normalize $PNR_NETLIST]"
if {$BATCH} { exit }
