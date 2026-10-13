# HPS h2f_user0_clock (100 MHz) drives all fabric logic in this design
create_clock -name h2f_user0_clk -period 10.000 [get_pins -compatibility_mode {*|fpga_interfaces|clocks_resets|h2f_user0_clk}]
derive_pll_clocks
derive_clock_uncertainty
# quasi-static SNN configuration registers (written only while idle)
set cfg_regs [get_registers -nowarn {*u_cls|th1[*] *u_cls|th2[*] *u_cls|leak[*] *u_cls|t_steps[*] *u_cls|b2[*] *u_cls|w2[*]}]
set_multicycle_path -setup 2 -from $cfg_regs
set_multicycle_path -hold  1 -from $cfg_regs
set_false_path -to [get_ports {FPGA_2V5_RF_LEDS_LED*}]
