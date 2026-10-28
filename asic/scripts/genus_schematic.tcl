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
#       SYNTH=1 genus -files scripts/genus_schematic.tcl       (slower, ~gate soup)
# Pick a sub-block to open instead of the whole chip:
#       SCHEM_TOP=snn_core genus -files scripts/genus_schematic.tcl
# ---------------------------------------------------------------------------
source scripts/setup.tcl

set TOPMOD [env_or SCHEM_TOP $DESIGN]
set DOSYN  [env_or SYNTH 0]

# ---- libraries + RTL (same sources as the synthesis flow) ----
set_db init_lib_search_path $LIB_DIR
set_db init_hdl_search_path $RTL_DIR
read_libs [file tail $SLOW_LIB]
read_hdl -v2001 $RTL_FILES
elaborate $DESIGN
puts "== elaborated $DESIGN"

if {$DOSYN} {
    # constraints so synthesis is meaningful, then map to gsclib090 cells
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
puts "   2. Right-click it -> 'Show Schematic'  (or Windows -> New -> Schematic)."
puts "   3. Double-click any block to descend into it."
puts "   4. Screenshot it: in the schematic window  File -> Save Image..."
puts "      (or use the OS screenshot tool)."
puts "  Leave Genus running while you capture; type 'exit' here when done."
puts "============================================================"
# NB: no 'exit' - keep the session (and the GUI) alive.
