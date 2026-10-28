# xrun -input for the GUI: record everything to SHM, run to $finish,
# and LEAVE SimVision open so the waveforms can be inspected.
database -open waves -shm -default
probe -create tb_snn_asic -depth all -all -shm -database waves
run
# (no 'exit' here, unlike xrun_batch.tcl / xrun_waves.tcl - keep the GUI up)
