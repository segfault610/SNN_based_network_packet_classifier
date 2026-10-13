#!/usr/bin/env bash
# Gate-level functional simulation of the Tang Nano 9K design AFTER Yosys synthesis
# (synth_gowin: LUT4/ALU/DFF/BSRAM cells) against the golden model.
# Same RTL as the bitstream; only the UART divider is set to 4 to keep the sim short.
# Gowin BSRAM behaviour comes from gowin_bsram_models.v (yosys ships blackboxes only).
set -e
cd "$(dirname "$0")"
export PATH=/opt/oss-cad-suite/bin:$PATH
R=../rtl
mkdir -p work_gl_tmp
yosys -q -p "read_verilog $R/sync_fifo.v $R/pkt_parser.v $R/spike_encoder.v $R/snn_core.v $R/snn_classifier.v \
      $R/snn_pkt_filter.v $R/uart.v ../fpga/tang9k/tang9k_snn_top.v; chparam -set CLKS_PER_BIT 4 tang9k_snn_top; \
      synth_gowin -top tang9k_snn_top; write_verilog -noattr work_gl_tmp/tang9k_gl.v"
rm -rf work_gl && vlib work_gl >/dev/null
vlog -quiet -timescale 1ns/1ps -work work_gl /opt/oss-cad-suite/share/yosys/gowin/cells_sim.v gowin_bsram_models.v work_gl_tmp/tang9k_gl.v
vlog -quiet -sv -work work_gl tb_tang9k.sv
vsim -c -lib work_gl tb_tang9k -gN_FRAMES=${N_FRAMES:-60} +nospecify +notimingchecks -suppress 2732 \
     -voptargs="-suppress 2732 +nospecify +notimingchecks" -do "run -all; quit -f" | tee sim_tang9k_gl.log \
     | grep -E 'ERR|RESULT|Tang9K'
rm -rf work_gl work_gl_tmp
