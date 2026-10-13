# qsys-script: add the SNN classifier to the Chameleon96 system
package require -exact qsys 16.0
load_system CV96_QSYS.qsys
add_instance snn_0 snn_lookaside
add_connection hps_0.h2f_user0_clock snn_0.clock
add_connection reset_bridge_0.out_reset snn_0.reset
add_connection hps_0.h2f_lw_axi_master snn_0.s0
set_connection_parameter_value hps_0.h2f_lw_axi_master/snn_0.s0 baseAddress 0x00010000
add_connection hps_0.f2h_irq0 snn_0.irq
set_connection_parameter_value hps_0.f2h_irq0/snn_0.irq irqNumber 1
add_interface snn_leds conduit end
set_interface_property snn_leds EXPORT_OF snn_0.leds
save_system CV96_QSYS.qsys
