// Conformal LEC (set DESIGN first, e.g. "setenv DESIGN snn_core" in the shell)
// Conformal LEC: RTL vs Genus netlist.  Run from asic/:  DESIGN=snn_core lec -xl -nogui -dofile scripts/lec.tcl
// (Conformal dofile syntax; tcl_mode off)
setenv RTL ../rtl
// $DESIGN comes from the shell environment
read library /home/cadence/install/FOUNDRY/digital/90nm/dig/lib/slow.lib -liberty -both
read design $RTL/sync_fifo.v $RTL/pkt_parser.v $RTL/spike_encoder.v $RTL/snn_core.v $RTL/snn_classifier.v $RTL/snn_pkt_filter.v $RTL/snn_pkt_filter_asic.v -verilog2k -golden -root $DESIGN
read design out/$DESIGN/$DESIGN\_netlist.v -verilog -revised -root $DESIGN
set flatten model -seq_constant
set analyze option -auto
set system mode lec
add compared points -all
compare
report verification
report compare data -class nonequivalent
exit -force
