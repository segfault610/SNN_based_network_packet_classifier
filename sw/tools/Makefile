# Cross-compile for the Chameleon96 Yocto image (static, no runtime deps)
YOCTO   ?= $(HOME)/Tools/Yocto/bitbake-builds/build/tmp
SYSROOT ?= $(firstword $(wildcard $(YOCTO)/work/cortexa9t2hf-neon-poky-linux-gnueabi/coreutils/*/recipe-sysroot))
XTC     ?= ../kmod/.xtc
CC       = $(XTC)/arm-poky-linux-gnueabi-gcc -B$(XTC)/ --sysroot=$(SYSROOT) -march=armv7-a -mfpu=neon -mfloat-abi=hard
snn_fwctl: snn_fwctl.c ../snn_regs.h
	$(CC) -O2 -Wall -static -I.. -o $@ $<
clean:
	rm -f snn_fwctl
