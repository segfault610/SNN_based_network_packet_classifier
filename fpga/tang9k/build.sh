#!/usr/bin/env bash
# Open-source build for the Tang Nano 9K: yosys -> nextpnr-himbaechel -> gowin_pack
#   ./build.sh            build tang9k_snn.fs
#   ./build.sh prog       build + load to SRAM with openFPGALoader (-f to flash)
set -e
cd "$(dirname "$0")"
export PATH=/opt/oss-cad-suite/bin:$PATH
R=../../rtl
yosys -q -l yosys.log -p "read_verilog $R/sync_fifo.v $R/pkt_parser.v $R/spike_encoder.v $R/snn_core.v \
      $R/snn_classifier.v $R/snn_pkt_filter.v $R/uart.v tang9k_snn_top.v; \
      synth_gowin -top tang9k_snn_top -json tang9k_snn.json"
nextpnr-himbaechel --json tang9k_snn.json --write tang9k_snn_pnr.json --device GW1NR-LV9QN88PC6/I5 \
      --vopt family=GW1N-9C --vopt cst=tang9k.cst --freq 27 -l nextpnr.log
gowin_pack -d GW1N-9C -o tang9k_snn.fs tang9k_snn_pnr.json
echo "bitstream: $PWD/tang9k_snn.fs"
if [ "$1" == "prog" ]; then openFPGALoader -b tangnano9k tang9k_snn.fs; fi
