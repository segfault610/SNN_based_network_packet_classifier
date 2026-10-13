# Out-of-tree build of snn_fw.ko against the Yocto kernel (no changes to the Yocto tree):
#   make            -> prepares a private copy of the kernel build dir once, then builds
YOCTO   ?= $(HOME)/Tools/Yocto/bitbake-builds/build/tmp
KSRC    ?= $(YOCTO)/work-shared/cyclone5/kernel-source
KART    ?= $(YOCTO)/work-shared/cyclone5/kernel-build-artifacts
KBUILD  ?= $(CURDIR)/.kbuild
XTC     ?= $(CURDIR)/.xtc
XPFX    := $(XTC)/arm-poky-linux-gnueabi-
KMAKE    = $(MAKE) -C $(KSRC) O=$(KBUILD) ARCH=arm CROSS_COMPILE=$(XPFX) CC="$(XPFX)gcc -B$(XTC)/"

obj-m := snn_fw.o

all: $(KBUILD)/scripts/mod/modpost
	$(KMAKE) M=$(CURDIR) modules

# toolchain: gcc-cross + binutils-cross from the Yocto sysroots, 'as'/'ld' reachable via -B
$(XTC)/arm-poky-linux-gnueabi-gcc:
	mkdir -p $(XTC)
	for f in $(YOCTO)/sysroots-components/x86_64/binutils-cross-arm/usr/bin/arm-poky-linux-gnueabi/* \
	         $(YOCTO)/sysroots-components/x86_64/gcc-cross-arm/usr/bin/arm-poky-linux-gnueabi/*; do ln -sf $$f $(XTC)/; done
	ln -sf $(XPFX)as $(XTC)/as; ln -sf $(XPFX)ld $(XTC)/ld

$(KBUILD)/scripts/mod/modpost: $(XTC)/arm-poky-linux-gnueabi-gcc
	rm -rf $(KBUILD); cp -a $(KART) $(KBUILD)
	$(KMAKE) -s olddefconfig modules_prepare

clean:
	rm -f *.o *.ko *.mod *.mod.c .*.cmd modules.order Module.symvers
distclean: clean
	rm -rf $(KBUILD) $(XTC)
