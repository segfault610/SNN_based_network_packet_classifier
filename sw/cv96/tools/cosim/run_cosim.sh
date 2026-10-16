#!/usr/bin/env bash
# Build snn_test against the accelerator RTL (Verilator) and run it on the laptop.
#   ./run_cosim.sh [snn_test arguments]      e.g. ./run_cosim.sh   |  ./run_cosim.sh C9  |  ./run_cosim.sh demo 0
set -e
cd "$(dirname "$0")"
R=../../../../rtl
V=$(command -v verilator || echo /opt/oss-cad-suite/bin/verilator)
python3 ../gen_vectors.py ../../../../sim/vectors ../vectors.h > /dev/null
if [ ! -x obj_dir/snn_test_cosim ] || [ -n "$(find $R ../snn_test.c ../hw.h ../vectors.h hw_verilator.cpp -newer obj_dir/snn_test_cosim 2>/dev/null)" ]; then
  $V --cc --exe --build -j 8 -O2 -Wno-fatal -Wno-lint --top-module snn_lookaside_avmm \
     -CFLAGS "-I$PWD/.. -O2" -o snn_test_cosim \
     $R/sync_fifo.v $R/pkt_parser.v $R/spike_encoder.v $R/snn_core.v $R/snn_classifier.v $R/snn_lookaside_avmm.v \
     hw_verilator.cpp ../snn_test.c > build.log 2>&1 || { tail -30 build.log; exit 1; }
fi
./obj_dir/snn_test_cosim "$@"
