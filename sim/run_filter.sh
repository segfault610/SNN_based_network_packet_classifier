#!/usr/bin/env bash
# Questa/ModelSim regression for snn_pkt_filter (run from anywhere).
#   ./run_filter.sh          batch mode
#   ./run_filter.sh gui      opens vsim GUI with waves
set -e
cd "$(dirname "$0")"
RTL=../rtl
rm -rf work && vlib work >/dev/null
vlog -quiet -lint $RTL/sync_fifo.v $RTL/pkt_parser.v $RTL/spike_encoder.v $RTL/snn_core.v $RTL/snn_classifier.v $RTL/snn_pkt_filter.v
vlog -quiet -sv tb_snn_pkt_filter.sv
if [ "$1" == "gui" ]; then
  vsim -voptargs=+acc tb_snn_pkt_filter -do "add wave -r /tb_snn_pkt_filter/dut/*; run -all"
else
  vsim -c -voptargs=+acc tb_snn_pkt_filter -do "run -all; quit -f" | tee sim_filter.log | grep -vE '^# (Loading|//)' 
fi
if [ "$1" != "gui" ]; then
  echo "=== stress (overflow / rollback) ==="
  vsim -c tb_snn_pkt_filter -gSTRESS=1 -gTREADY_PCT=35 -gIFG_MIN=1 -gIFG_MAX=3 -do "run -all; quit -f" \
    | tee sim_filter_stress.log | grep -E 'ERR|WARN|RESULT|frames|counters'
fi
