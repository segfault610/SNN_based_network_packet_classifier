#!/usr/bin/env bash
# Open-source ASIC synthesis: Yosys + ABC onto SkyWater sky130_fd_sc_hd (tt, 25C, 1.8V)
#   ./synth.sh [top]     top = snn_core (default) | snn_classifier | snn_pkt_filter_asic
# Memories are synthesised as flip-flops here (no SRAM macros) - area is pessimistic.
set -e
cd "$(dirname "$0")"
TOP=${1:-snn_core}
LIB=/usr/local/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
R=../../rtl
export PATH=/opt/oss-cad-suite/bin:$PATH
mkdir -p out
yosys -q -l out/${TOP}_yosys.log -p "
  read_verilog $R/sync_fifo.v $R/pkt_parser.v $R/spike_encoder.v $R/snn_core.v $R/snn_classifier.v \
               $R/snn_pkt_filter.v $R/snn_pkt_filter_asic.v
  synth -top $TOP -flatten
  dfflibmap -liberty $LIB
  abc -D 8000 -liberty $LIB -dont_use sky130_fd_sc_hd__lpflow_*
  opt_clean -purge
  tee -o out/${TOP}_area.rpt stat -liberty $LIB
  write_verilog -noattr out/${TOP}_sky130_netlist.v"
grep -E "Chip area|cells$" out/${TOP}_area.rpt | tail -2
grep -E "ABC: .*Delay =" out/${TOP}_yosys.log | tail -1 | sed 's/.*Area/Area/' | tee out/${TOP}_timing.rpt
