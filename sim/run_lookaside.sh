#!/usr/bin/env bash
# Look-aside accelerator (Chameleon96 / Linux kernel hook) regression.
set -e
cd "$(dirname "$0")"
RTL=../rtl
rm -rf work_la && vlib work_la >/dev/null
vlog -quiet -lint -work work_la $RTL/sync_fifo.v $RTL/pkt_parser.v $RTL/spike_encoder.v $RTL/snn_core.v \
     $RTL/snn_classifier.v $RTL/snn_lookaside_avmm.v
vlog -quiet -sv -work work_la tb_snn_lookaside.sv
vsim -c -lib work_la -voptargs=+acc tb_snn_lookaside -do "run -all; quit -f" | tee sim_lookaside.log | grep -E 'ERR|RESULT|look-aside|truth|avg|Error|Warning'
