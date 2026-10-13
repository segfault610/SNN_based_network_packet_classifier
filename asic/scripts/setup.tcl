# ---------------------------------------------------------------------------
# Shared settings for every Cadence step (Genus, Conformal, Innovus).
# All tools are started from the asic/ directory. Anything here can be overridden
# from the shell, e.g.  DESIGN=snn_core CLK_OPTIMAL=7.0 genus -files scripts/genus_optimal.tcl
# ---------------------------------------------------------------------------
if {![file exists ../rtl/snn_core.v]} {
    error "start the Cadence tools from the asic/ directory (../rtl must exist)"
}
proc env_or {name def} {
    if {[info exists ::env($name)]} { return $::env($name) }
    return $def
}

# ---- design: snn_pkt_filter_asic = full in-line firewall (buffer + parser + encoder + SNN)
#               snn_classifier      = parser + encoder + SNN only
#               snn_core            = SNN only
set DESIGN    [env_or DESIGN snn_pkt_filter_asic]
set RTL_DIR   ../rtl
set RTL_FILES {sync_fifo.v pkt_parser.v spike_encoder.v snn_core.v snn_classifier.v
               snn_pkt_filter.v snn_pkt_filter_asic.v}
set RTL_PATHS {}
foreach f $RTL_FILES { lappend RTL_PATHS $RTL_DIR/$f }

# ---- technology: Cadence GPDK 90 nm, gsclib090
set PDK       [env_or GPDK090 /home/cadence/install/FOUNDRY/digital/90nm/dig]
set LIB_DIR   $PDK/lib
set SLOW_LIB  $LIB_DIR/slow.lib            ;# worst case: synthesis + setup
set FAST_LIB  $LIB_DIR/fast.lib            ;# best case: hold
if {![file exists $FAST_LIB]} { set FAST_LIB $SLOW_LIB }
set TECH_LEF  $PDK/lef/gsclib090_translated.lef
set CAP_TABLE [env_or CAP_TABLE ""]        ;# optional .capTbl for Innovus extraction

# ---- the three synthesis variants (clock period in ns)
#   fast    : performance target, 200 MHz, high effort
#   optimal : the system requirement, 125 MHz = 1 GbE GMII byte clock (used for PD)
#   slow    : relaxed, 83 MHz, low effort -> smallest / lowest-power netlist
array set PERIOD [list \
    fast    [env_or CLK_FAST    5.0] \
    optimal [env_or CLK_OPTIMAL 8.0] \
    slow    [env_or CLK_SLOW   12.0]]
array set EFFORT {
    fast    {high   high   high}
    optimal {medium high   high}
    slow    {low    low    low}
}

# ---- output tree:  out/<DESIGN>/{syn_fast,syn_optimal,syn_slow,lec,pnr,sim}
set OUT out/$DESIGN
proc syn_dir     {v} { return $::OUT/syn_$v }
proc tm_netlist  {v} { return $::OUT/syn_$v/${::DESIGN}_tm_netlist_$v.v }
proc tm_sdc      {v} { return $::OUT/syn_$v/${::DESIGN}_$v.sdc }
set PNR_VARIANT  [env_or PNR_VARIANT optimal]
set PNR_DIR      $OUT/pnr
set PNR_NETLIST  $PNR_DIR/${DESIGN}_pnr_netlist.v
set PNR_SDF      $PNR_DIR/${DESIGN}_pnr.sdf

# batch mode (scripts/run_flow.sh sets BATCH=1): each step exits when done
set BATCH [env_or BATCH 0]
