# xrun -input: record all signals to an SHM database (open with simvision waves.shm)
database -open waves -shm -default
probe -create tb_snn_asic -depth all -all -shm -database waves
run
exit
