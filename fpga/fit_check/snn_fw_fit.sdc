create_clock -name clk -period 8.000 [get_ports clk]
derive_clock_uncertainty
set_false_path -to [get_ports leds*]
# Quasi-static configuration registers (written by software only while the
# classifier is idle / before enabling traffic): 2-cycle paths.
set cfg_regs [get_registers {*u_cls|leak[*] *u_cls|th1[*] *u_cls|th2[*] *u_cls|t_steps[*] *u_cls|b2[*] *u_cls|w2[*] *u_fw|drop_en *u_fw|bypass}]
set_multicycle_path -setup 2 -from $cfg_regs
set_multicycle_path -hold  1 -from $cfg_regs
