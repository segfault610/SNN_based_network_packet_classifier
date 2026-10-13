#!/usr/bin/env bash
# Chameleon96 simulations (the logic inside cv96_snn.rbf), sim/cv96/run.sh <mode>
#   lookaside  snn_lookaside_avmm, the accelerator on the LW H2F bridge (0xFF210000): register-level
#              sequence the kernel module / snn_fwctl use (header window, SUBMIT, VERDICT polling,
#              IRQ, stats), verdicts bit-exact vs golden model
#   avmm       snn_fw_avmm, the in-line filter behind an Avalon-MM slave (HPS bring-up path)
#   gui        lookaside in the vsim GUI with waves
#   all        lookaside avmm  (default)
TGT=$(cd "$(dirname "$0")" && pwd); source "$TGT/../common.sh"

mode() {
  case $1 in
    lookaside|gui)
      newlib la
      vlog -quiet -lint -work work_la $CORE $RTL/snn_lookaside_avmm.v
      vlog -quiet -sv -work work_la $TGT/tb_snn_lookaside.sv
      if [ $1 == gui ]; then
        vsim -lib work_la -voptargs=+acc tb_snn_lookaside -gVEC_DIR=$VEC -do "add wave -r /tb_snn_lookaside/*; run -all"
      else
        sim la tb_snn_lookaside lookaside.log 'ERR|RESULT|look-aside|truth|avg|Error' -voptargs=+acc -gVEC_DIR=$VEC
      fi ;;
    avmm)
      newlib avmm
      vlog -quiet -lint -work work_avmm $CORE $RTL/snn_pkt_filter.v $RTL/snn_fw_avmm.v
      vlog -quiet -sv -work work_avmm $TGT/tb_snn_fw_avmm.sv
      sim avmm tb_snn_fw_avmm avmm.log 'ERR|RESULT|AVMM|Error' -voptargs=+acc -gVEC_DIR=$VEC ;;
    all) for m in lookaside avmm; do echo "--- cv96/$m"; mode $m; done ;;
    *) usage ;;
  esac
}
mode "${1:-all}"
