#!/usr/bin/env bash
# Tang Nano 9K in-line firewall top: UART/SLIP-level simulation
set -e
cd "$(dirname "$0")"
RTL=../rtl
rm -rf work_tang && vlib work_tang >/dev/null
vlog -quiet -lint -work work_tang $RTL/sync_fifo.v $RTL/pkt_parser.v $RTL/spike_encoder.v $RTL/snn_core.v \
     $RTL/snn_classifier.v $RTL/snn_pkt_filter.v $RTL/uart.v ../fpga/tang9k/tang9k_snn_top.v
vlog -quiet -sv -work work_tang tb_tang9k.sv
vsim -c -lib work_tang -voptargs=+acc tb_tang9k -do "run -all; quit -f" | tee sim_tang9k.log | grep -E 'ERR|RESULT|Tang9K|Error|Warning'
