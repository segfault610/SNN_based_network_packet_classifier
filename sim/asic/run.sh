#!/usr/bin/env bash
# ASIC / in-line NIC datapath simulations (Questa), sim/asic/run.sh <mode>
#   filter     snn_pkt_filter vs golden model: every spike vector, verdict and forwarded byte
#   stress     same filter, 35 % egress ready + 1-3 cycle gaps: drops / rollback / counter integrity
#   mac        verilog-ethernet eth_mac_1g with the filter fused into RX, driven at the GMII pins
#   suite      snn_pkt_filter_asic, port-level functional suite T1..T10 (docs/functional_verification.md)
#   suite-gl   the same suite on the Yosys -> sky130_fd_sc_hd netlist with sky130 cell models
#   gui        suite in the vsim GUI with waves
#   all        filter stress mac suite suite-gl  (default)
# The Cadence/Xcelium version of the suite: asic/scripts/run_flow.sh sim-rtl | sim-gls | sim-sdf
TGT=$(cd "$(dirname "$0")" && pwd); source "$TGT/../common.sh"
FILTER="$CORE $RTL/snn_pkt_filter.v"
ASIC="$FILTER $RTL/snn_pkt_filter_asic.v"
ETH=$ROOT/third_party/verilog-ethernet

mode() {
  case $1 in
    filter|stress)
      newlib filter
      vlog -quiet -lint -work work_filter $FILTER
      vlog -quiet -sv -work work_filter $TGT/tb_snn_pkt_filter.sv
      if [ $1 == filter ]; then
        sim filter tb_snn_pkt_filter filter.log 'ERR|RESULT|frames|counters|detection' -gVEC_DIR=$VEC
      else
        sim filter tb_snn_pkt_filter stress.log 'ERR|WARN|RESULT|frames|counters' -gVEC_DIR=$VEC \
            -gSTRESS=1 -gTREADY_PCT=35 -gIFG_MIN=1 -gIFG_MAX=3
      fi ;;
    mac)
      newlib mac
      vlog -quiet -work work_mac $ETH/rtl/eth_mac_1g.v $ETH/rtl/axis_gmii_rx.v $ETH/rtl/axis_gmii_tx.v $ETH/rtl/lfsr.v \
           $ETH/rtl/mac_ctrl_rx.v $ETH/rtl/mac_ctrl_tx.v $ETH/rtl/mac_pause_ctrl_rx.v $ETH/rtl/mac_pause_ctrl_tx.v \
           $ETH/lib/axis/rtl/axis_async_fifo.v $ETH/lib/axis/rtl/axis_async_fifo_adapter.v $ETH/lib/axis/rtl/axis_adapter.v
      vlog -quiet -work work_mac $FILTER $RTL/eth_mac_1g_snn_fifo.v
      vlog -quiet -sv -work work_mac $TGT/tb_eth_mac_snn.sv
      sim mac tb_eth_mac_snn mac.log 'ERR|RESULT|frames|Error' -voptargs=+acc -gVEC_DIR=$VEC ;;
    suite|gui)
      newlib suite
      vlog -quiet -lint -work work_suite $ASIC
      vlog -quiet -sv -work work_suite $TGT/tb_snn_asic.sv
      if [ $1 == gui ]; then
        vsim -lib work_suite -voptargs=+acc tb_snn_asic +VEC_DIR=$VEC -do "add wave -r /tb_snn_asic/*; run -all"
      else
        sim suite tb_snn_asic suite.log '^# +(PASS|FAIL|\[ERR\]|RESULT|frames=|sent=|vs ground)' +VEC_DIR=$VEC
      fi ;;
    suite-gl)
      P=/usr/local/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/verilog
      $ROOT/asic/sky130/synth.sh snn_pkt_filter_asic > synth_sky130.log 2>&1
      newlib suite_gl
      vlog -quiet -work work_suite_gl -suppress 2263,2241 +define+FUNCTIONAL +define+UNIT_DELAY= \
           $P/primitives.v $P/sky130_fd_sc_hd.v > /dev/null
      vlog -quiet -work work_suite_gl $ROOT/asic/sky130/out/snn_pkt_filter_asic_sky130_netlist.v
      vlog -quiet -sv -work work_suite_gl $TGT/tb_snn_asic.sv
      sim suite_gl tb_snn_asic suite_gl.log '^# +(PASS|FAIL|\[ERR\]|RESULT|frames=|sent=|vs ground)' +VEC_DIR=$VEC ;;
    all) for m in filter stress mac suite suite-gl; do echo "--- asic/$m"; mode $m; done ;;
    *) usage ;;
  esac
}
mode "${1:-all}"
