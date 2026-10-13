# ---------------------------------------------------------------------------
# Compare the three Genus variants and publish the main technology-mapped netlist.
#   from asic/:   tclsh scripts/genus_summary.tcl        (after genus_fast/optimal/slow)
# Writes  out/<DESIGN>/qor_summary.txt               slack / area / power per variant
#         out/<DESIGN>/<DESIGN>_tm_netlist.v (+ .sdc) = the PNR_VARIANT netlist (optimal)
# ---------------------------------------------------------------------------
source scripts/setup.tcl

proc grab {file patterns} {
    if {![file exists $file]} { return [list "  (missing: $file)"] }
    set fi [open $file r]; set lines [split [read $fi] \n]; close $fi
    set out {}
    foreach l $lines {
        foreach p $patterns { if {[regexp -nocase $p $l]} { lappend out "  [string trim $l]"; break } }
    }
    return $out
}

set fo [open $OUT/qor_summary.txt w]
foreach v {fast optimal slow} {
    set rpt [syn_dir $v]/reports
    puts $fo "==== $v: clock period $PERIOD($v) ns ([format %.1f [expr {1000.0/$PERIOD($v)}]] MHz), effort [join $EFFORT($v) /]"
    if {![file exists [tm_netlist $v]]} { puts $fo "  not synthesised yet (genus -files scripts/genus_$v.tcl)"; continue }
    foreach l [grab $rpt/qor.rpt {slack {total area} {cell area} {leaf instance} {sequential instance}
                                  {total power} {leakage power} {dynamic power} {violating paths}}] { puts $fo $l }
    foreach l [grab $rpt/timing.rpt {^\s*slack}] { puts $fo "  timing.rpt:$l"; break }
}
close $fo

foreach ext {v sdc} src [list [tm_netlist $PNR_VARIANT] [tm_sdc $PNR_VARIANT]] {
    if {[file exists $src]} { file copy -force $src $OUT/${DESIGN}_tm_netlist.$ext }
}
set fi [open $OUT/qor_summary.txt r]; puts [read $fi]; close $fi
puts "main netlist: $OUT/${DESIGN}_tm_netlist.v  (= $PNR_VARIANT variant)"
