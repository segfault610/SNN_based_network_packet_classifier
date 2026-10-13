# Platform Designer component: SNN look-aside packet classifier
package require -exact qsys 16.0

set_module_property NAME snn_lookaside
set_module_property VERSION 1.0
set_module_property DISPLAY_NAME "SNN look-aside packet classifier"
set_module_property GROUP "Custom"
set_module_property AUTHOR "SNN_based_network_packet_classifier"
set_module_property INSTANTIATE_IN_SYSTEM_MODULE true
set_module_property EDITABLE false

add_fileset QUARTUS_SYNTH QUARTUS_SYNTH "" ""
set_fileset_property QUARTUS_SYNTH TOP_LEVEL snn_lookaside_avmm
foreach f {sync_fifo pkt_parser spike_encoder snn_core snn_classifier snn_lookaside_avmm} {
    add_fileset_file $f.v VERILOG PATH ../../../../rtl/$f.v
}

add_interface clock clock end
add_interface_port clock clk clk Input 1

add_interface reset reset end
set_interface_property reset associatedClock clock
set_interface_property reset synchronousEdges DEASSERT
add_interface_port reset reset reset Input 1

add_interface s0 avalon end
set_interface_property s0 addressUnits WORDS
set_interface_property s0 associatedClock clock
set_interface_property s0 associatedReset reset
set_interface_property s0 readLatency 1
set_interface_property s0 maximumPendingReadTransactions 0
set_interface_property s0 readWaitTime 0
set_interface_property s0 writeWaitTime 0
add_interface_port s0 avs_address address Input 11
add_interface_port s0 avs_write write Input 1
add_interface_port s0 avs_writedata writedata Input 32
add_interface_port s0 avs_read read Input 1
add_interface_port s0 avs_readdata readdata Output 32

add_interface irq interrupt end
set_interface_property irq associatedAddressablePoint s0
set_interface_property irq associatedClock clock
set_interface_property irq associatedReset reset
add_interface_port irq irq irq Output 1

add_interface leds conduit end
add_interface_port leds leds export Output 2
