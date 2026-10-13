project_open snn_fw_fit
create_timing_netlist
read_sdc
update_timing_netlist
report_timing -setup -npaths 8 -detail summary -file paths.rpt
