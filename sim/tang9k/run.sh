#!/usr/bin/env bash
# Tang Nano 9K simulations, sim/tang9k/run.sh <mode>
#   rtl     tang9k_snn_top (UART + SLIP + in-line filter) vs golden model, Questa
#   gl      the same after Yosys synth_gowin (the netlist that goes into the bitstream), Questa
#           Gowin BSRAM behaviour from gowin_bsram_models.v; UART divider 4 to keep it short
#   host    PC side: sw/tang9k/tang_demo.py against sw/tang9k/fake_tang.py (golden model on a pty),
#           i.e. the demo script exactly as you'd run it on the board, no hardware needed
#   gui     rtl in the vsim GUI with waves
#   all     rtl gl host  (default)
TGT=$(cd "$(dirname "$0")" && pwd); source "$TGT/../common.sh"
TOP_SRC="$CORE $RTL/snn_pkt_filter.v $RTL/uart.v $ROOT/fpga/tang9k/tang9k_snn_top.v"

mode() {
  case $1 in
    rtl|gui)
      newlib rtl
      vlog -quiet -lint -work work_rtl $TOP_SRC
      vlog -quiet -sv -work work_rtl $TGT/tb_tang9k.sv
      if [ $1 == gui ]; then
        vsim -lib work_rtl -voptargs=+acc tb_tang9k -gVEC_DIR=$VEC -do "add wave -r /tb_tang9k/*; run -all"
      else
        sim rtl tb_tang9k rtl.log 'ERR|RESULT|Tang9K|Error' -voptargs=+acc -gVEC_DIR=$VEC
      fi ;;
    gl)
      $OSS/bin/yosys -q -l synth_gowin.log -p "read_verilog $TOP_SRC; chparam -set CLKS_PER_BIT 4 tang9k_snn_top; \
            synth_gowin -top tang9k_snn_top; write_verilog -noattr tang9k_gl.v"
      newlib gl
      vlog -quiet -timescale 1ns/1ps -work work_gl $OSS/share/yosys/gowin/cells_sim.v $TGT/gowin_bsram_models.v tang9k_gl.v
      vlog -quiet -sv -work work_gl $TGT/tb_tang9k.sv
      sim gl tb_tang9k gl.log 'ERR|RESULT|Tang9K' -gVEC_DIR=$VEC -gN_FRAMES=${N_FRAMES:-60} \
          +nospecify +notimingchecks -suppress 2732 -voptargs="-suppress 2732 +nospecify +notimingchecks" ;;
    host)
      # needs pyserial (tang_demo.py) + numpy (golden model): first interpreter that has both
      for PY in $ROOT/.venv/bin/python python3; do $PY -c "import serial, numpy" 2>/dev/null && break; done
      $PY -c "import serial, numpy" 2>/dev/null || { echo "Error: pip install pyserial numpy"; return; }
      $PY -u $ROOT/sw/tang9k/fake_tang.py > fake_tang.out 2>&1 &
      fake=$!
      for i in $(seq 50); do [ -s fake_tang.out ] && break; sleep 0.1; done
      port=$(head -1 fake_tang.out)
      timeout 300 $PY $ROOT/sw/tang9k/tang_demo.py --port $port --max ${N_FRAMES:-200} > host.log 2>&1 || true
      kill $fake 2>/dev/null || true
      grep -E 'link|bit-exact|identical|RESULT|Error|Traceback' host.log ;;
    all) for m in rtl gl host; do echo "--- tang9k/$m"; mode $m; done ;;
    *) usage ;;
  esac
}
mode "${1:-all}"
