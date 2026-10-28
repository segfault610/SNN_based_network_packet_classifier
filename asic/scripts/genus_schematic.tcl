# ---------------------------------------------------------------------------
# Open the FULL design (snn_pkt_filter_asic) in the Genus GUI schematic viewer,
# so you can browse the hierarchy and grab a screenshot.
#
#   from asic/ (needs an X display - do NOT pass -no_gui):
#       genus -files scripts/genus_schematic.tcl
#   over SSH, enable X first:   ssh -Y user@cadence-server
#
# Default = RTL / elaborated schematic (fast, readable: adders, muxes, regs,
# comparators). For the technology-MAPPED gate schematic instead:
#       SCHEM_GATE=1 genus -files scripts/genus_schematic.tcl    (slower, ~gate soup)
# Pick a sub-block to open instead of the whole chip:
#       SCHEM_TOP=snn_core genus -files scripts/genus_schematic.tcl
#
# NB: the toggle env var is SCHEM_GATE, NOT "SYNTH" - some Cadence site setups
# export SYNTH as the Genus install path, which would break a boolean test.
# ---------------------------------------------------------------------------
source scripts/setup.tcl

# which module's schematic to view (default: the whole chip)
set TOPMOD $DESIGN
if {[info exists ::env(SCHEM_TOP)] && $::env(SCHEM_TOP) ne ""} {
    set TOPMOD $::env(SCHEM_TOP)
}
# gate-level (mapped) schematic? only when SCHEM_GATE is exactly 1/true/yes/on
set DOSYN 0
if {[info exists ::env(SCHEM_GATE)]} {
    switch -nocase -- [string trim $::env(SCHEM_GATE)] {
        1 - true - yes - on { set DOSYN 1 }
    }
}

# ---- libraries + RTL (same sources as the synthesis flow) ----
set_db init_lib_search_path $LIB_DIR
set_db init_hdl_search_path $RTL_DIR
read_libs [file tail $SLOW_LIB]
read_hdl -v2001 $RTL_FILES
elaborate $DESIGN
puts "== elaborated $DESIGN"

if {$DOSYN == 1} {
    set fi [open constraints/snn.sdc r]; set sdc [read $fi]; close $fi
    regsub {set CLK_PERIOD [0-9.]+} $sdc "set CLK_PERIOD $PERIOD(optimal)" sdc
    set tmp out/$DESIGN/schem_in.sdc
    file mkdir [file dirname $tmp]
    set fo [open $tmp w]; puts $fo $sdc; close $fo
    read_sdc $tmp
    syn_generic
    syn_map
    puts "== synthesised (technology-mapped) $DESIGN"
}

# ---- open the GUI ----
gui_show

puts "============================================================"
puts "  Genus GUI is open. To see the schematic of '$TOPMOD':"
puts "   1. In the left hierarchy/browser, select module '$TOPMOD'."
puts "   2. Right-click it -> 'Show Schematic' (or Windows -> New -> Schematic)."
puts "   3. Double-click any block to descend into it."
puts "   4. Screenshot: in the schematic window  File -> Save Image..."
puts "  Leave Genus running while you capture; type 'exit' here when done."
puts "============================================================"
# no 'exit' - keep the session (and the GUI) alive.
