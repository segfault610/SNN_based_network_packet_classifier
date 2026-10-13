# 125 MHz = 1 GbE GMII byte clock (8 ns). Tighten to 4 ns to explore 2.5G.
set CLK_PERIOD 8.0
create_clock -name clk -period $CLK_PERIOD [get_ports clk]
set_clock_transition 0.1 [get_clocks clk]
set_clock_uncertainty 0.1 [get_clocks clk]
set_input_delay  [expr 0.2*$CLK_PERIOD] -clock clk [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay [expr 0.2*$CLK_PERIOD] -clock clk [all_outputs]
set_load 0.01 [all_outputs]
