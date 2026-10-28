# Clock + IO constraints. CLK_PERIOD is replaced per variant by genus_core.tcl (fast 5 / optimal 8 / slow 12 ns).
set CLK_PERIOD 5.0
create_clock -name clk -period $CLK_PERIOD [get_ports clk]
set_clock_transition 0.1 [get_clocks clk]
set_clock_uncertainty 0.1 [get_clocks clk]
set_input_delay  [expr 0.2*$CLK_PERIOD] -clock clk [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay [expr 0.2*$CLK_PERIOD] -clock clk [all_outputs]
set_load 0.01 [all_outputs]

