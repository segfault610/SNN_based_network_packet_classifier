#!/usr/bin/env bash
# ASIC top (snn_pkt_filter_asic) functional suite T1..T10, Questa.
#   ./run_asic.sh          RTL
#   ./run_asic.sh gl       gate-level: Yosys -> sky130_fd_sc_hd netlist + sky130 cell models
#                          (local stand-in for the Genus tm_netlist + gsclib090 GLS run with xrun)
#   ./run_asic.sh gui      RTL in the vsim GUI
# The same testbench runs under Xcelium: asic/scripts/run_flow.sh sim-rtl | sim-gls | sim-sdf
set -e
cd "$(dirname "$0")"
R=../rtl
RTL="$R/sync_fifo.v $R/pkt_parser.v $R/spike_encoder.v $R/snn_core.v $R/snn_classifier.v $R/snn_pkt_filter.v $R/snn_pkt_filter_asic.v"
rm -rf work_asic && vlib work_asic >/dev/null
if [ "$1" == "gl" ]; then
  P=/usr/local/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/verilog
  ../asic/sky130/synth.sh snn_pkt_filter_asic >/dev/null 2>&1
  vlog -work work_asic -quiet -suppress 2263,2241 +define+FUNCTIONAL +define+UNIT_DELAY= $P/primitives.v $P/sky130_fd_sc_hd.v >/dev/null
  vlog -work work_asic -quiet ../asic/sky130/out/snn_pkt_filter_asic_sky130_netlist.v
  LOG=sim_asic_gl.log
else
  vlog -work work_asic -quiet -lint $RTL
  LOG=sim_asic.log
fi
vlog -work work_asic -quiet -sv tb_snn_asic.sv
if [ "$1" == "gui" ]; then
  vsim -lib work_asic -voptargs=+acc tb_snn_asic -do "add wave -r /tb_snn_asic/*; run -all"
else
  vsim -c -lib work_asic tb_snn_asic -do "run -all; quit -f" | tee $LOG | grep -E '^# +(PASS|FAIL|\[ERR\]|RESULT|frames=|sent=|vs ground)' | sed 's/^# //'
fi
