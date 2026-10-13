# Standalone fit/timing check of snn_fw_avmm on the Chameleon96 Cyclone V SoC.
# Run: quartus_sh -t snn_fw_fit.tcl
load_package flow
project_new snn_fw_fit -overwrite
set_global_assignment -name FAMILY "Cyclone V"
set_global_assignment -name DEVICE 5CSEBA6U19I7
set_global_assignment -name TOP_LEVEL_ENTITY snn_fw_avmm
foreach f {sync_fifo pkt_parser spike_encoder snn_core snn_classifier snn_pkt_filter snn_fw_avmm} {
    set_global_assignment -name VERILOG_FILE ../../rtl/$f.v
}
set_global_assignment -name SDC_FILE snn_fw_fit.sdc
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
# Bus ports would be internal (Platform Designer) in the real system
foreach p {avs_address* avs_write avs_writedata* avs_read avs_readdata* avs_waitrequest reset} {
    set_instance_assignment -name VIRTUAL_PIN ON -to $p
}
set_location_assignment PIN_Y19 -to leds[0]
set_location_assignment PIN_Y20 -to leds[1]
set_instance_assignment -name IO_STANDARD "2.5 V" -to leds[0]
set_instance_assignment -name IO_STANDARD "2.5 V" -to leds[1]
execute_flow -compile
project_close
