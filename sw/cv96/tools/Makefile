# Cross-compile for the Chameleon96 Yocto image (static, no runtime deps)
#   make            -> snn_fwctl (weights, stats, self-test) and snn_test (C1..C10 board test, demo)
#   cosim/run_cosim.sh   -> the same snn_test against the RTL on the laptop (Verilator)
YOCTO   ?= $(HOME)/Tools/Yocto/bitbake-builds/build/tmp
SYSROOT ?= $(firstword $(wildcard $(YOCTO)/work/cortexa9t2hf-neon-poky-linux-gnueabi/coreutils/*/recipe-sysroot))
XTC     ?= ../kmod/.xtc
CC       = $(XTC)/arm-poky-linux-gnueabi-gcc -B$(XTC)/ --sysroot=$(SYSROOT) -march=armv7-a -mfpu=neon -mfloat-abi=hard
VEC      = ../../../sim/vectors

all: snn_fwctl snn_test

snn_fwctl: snn_fwctl.c ../snn_regs.h
	$(CC) -O2 -Wall -static -I.. -o $@ $<

vectors.h: gen_vectors.py $(VEC)/frames.txt $(VEC)/expected.txt $(VEC)/cfg.txt
	python3 gen_vectors.py $(VEC) $@

snn_test: snn_test.c snn_custom.c snn_custom.h hw_devmem.c hw.h vectors.h
	$(CC) -O2 -Wall -std=gnu99 -static -o $@ snn_test.c snn_custom.c hw_devmem.c

clean:
	rm -f snn_fwctl snn_test vectors.h
	rm -rf cosim/obj_dir cosim/build.log
