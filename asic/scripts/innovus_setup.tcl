# ---------------------------------------------------------------------------
# Innovus settings shared by every stage script (sourced by each of them).
# PD runs on the "optimal" Genus netlist: out/<DESIGN>/syn_optimal/<DESIGN>_tm_netlist_optimal.v
# (PNR_VARIANT=fast|slow in the shell selects another one).
# ---------------------------------------------------------------------------
source scripts/setup.tcl
set NETLIST   [tm_netlist $PNR_VARIANT]
set SDC_FILE  [tm_sdc $PNR_VARIANT]
set RPT_DIR   $PNR_DIR/reports
file mkdir $RPT_DIR

set VDD_NET   VDD
set VSS_NET   VSS

# floorplan: aspect ratio, core utilisation, core-to-die margins (um)
set FP_ASPECT [env_or FP_ASPECT 1.0]
set FP_UTIL   [env_or FP_UTIL   0.60]
set FP_MARGIN 10

# power grid (same layers as the snn_stdp flow that already ran on this PDK)
set RING_H    M8
set RING_V    M7
set STRIPE_H  M8
set STRIPE_V  M7
set PG_LAYERS {M1 M8}

# physical-only cells, used only if present in the LEF
set FILLER_CELLS {FILL64 FILL32 FILL16 FILL8 FILL4 FILL2 FILL1}
set TIE_CELLS    {TIEHI TIELO}

proc existing_cells {names} {
    set ok {}
    foreach c $names { if {[dbget head.libCells.name $c -e] ne ""} { lappend ok $c } }
    return $ok
}
proc save_stage {name} {
    saveDesign $::PNR_DIR/${::DESIGN}_$name.enc
    puts "==== stage $name saved: $::PNR_DIR/${::DESIGN}_$name.enc  (restore with: source $::PNR_DIR/${::DESIGN}_$name.enc)"
}
