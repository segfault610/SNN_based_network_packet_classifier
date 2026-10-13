// Xcelium file list: RTL functional verification of snn_pkt_filter_asic.
// Use with -F (paths are relative to this file):
//   cd asic && xrun -F scripts/xrun_rtl.f -input scripts/xrun_batch.tcl +VEC_DIR=$PWD/../sim/vectors
-64bit
-sv
-timescale 1ns/1ps
-access +r
-top tb_snn_asic
../../rtl/sync_fifo.v
../../rtl/pkt_parser.v
../../rtl/spike_encoder.v
../../rtl/snn_core.v
../../rtl/snn_classifier.v
../../rtl/snn_pkt_filter.v
../../rtl/snn_pkt_filter_asic.v
../../sim/tb_snn_asic.sv
