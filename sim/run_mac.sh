#!/usr/bin/env bash
# System test: verilog-ethernet 1G MAC with the SNN firewall fused into its RX path.
set -e
cd "$(dirname "$0")"
RTL=../rtl
ETH=../third_party/verilog-ethernet
rm -rf work_mac && vlib work_mac >/dev/null
vlog -quiet -work work_mac $ETH/rtl/eth_mac_1g.v $ETH/rtl/axis_gmii_rx.v $ETH/rtl/axis_gmii_tx.v $ETH/rtl/lfsr.v \
     $ETH/rtl/mac_ctrl_rx.v $ETH/rtl/mac_ctrl_tx.v $ETH/rtl/mac_pause_ctrl_rx.v $ETH/rtl/mac_pause_ctrl_tx.v \
     $ETH/lib/axis/rtl/axis_async_fifo.v $ETH/lib/axis/rtl/axis_async_fifo_adapter.v $ETH/lib/axis/rtl/axis_adapter.v
vlog -quiet -work work_mac $RTL/sync_fifo.v $RTL/pkt_parser.v $RTL/spike_encoder.v $RTL/snn_core.v $RTL/snn_classifier.v \
     $RTL/snn_pkt_filter.v $RTL/eth_mac_1g_snn_fifo.v
vlog -quiet -sv -work work_mac tb_eth_mac_snn.sv
vsim -c -lib work_mac -voptargs=+acc tb_eth_mac_snn -do "run -all; quit -f" | tee sim_mac.log | grep -E 'ERR|RESULT|frames|Error'
