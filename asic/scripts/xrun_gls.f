// Xcelium file list: gate-level simulation (Genus tm_netlist or Innovus netlist).
// The netlist, the gsclib090 cell models (-v) and the delay mode come from the command line;
// see scripts/run_flow.sh sim-gls / sim-sdf.
-64bit
-sv
-timescale 1ns/1ps
-access +r
-top tb_snn_asic
../../sim/asic/tb_snn_asic.sv
