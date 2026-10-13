#!/usr/bin/env bash
# Avalon-MM wrapper (FPGA / HPS bring-up path) regression.
set -e
cd "$(dirname "$0")"
RTL=../rtl
rm -rf work_avmm && vlib work_avmm >/dev/null
vlog -quiet -lint -work work_avmm $RTL/sync_fifo.v $RTL/pkt_parser.v $RTL/spike_encoder.v $RTL/snn_core.v $RTL/snn_classifier.v \
     $RTL/snn_pkt_filter.v $RTL/snn_fw_avmm.v
vlog -quiet -sv -work work_avmm tb_snn_fw_avmm.sv
vsim -c -lib work_avmm -voptargs=+acc tb_snn_fw_avmm -do "run -all; quit -f" | tee sim_avmm.log | grep -E 'ERR|RESULT|AVMM|Error|Warning'
