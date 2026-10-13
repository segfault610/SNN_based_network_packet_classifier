SUMMARY = "SNN FPGA packet firewall rx_handler kernel module + weights"
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
inherit module
# Points at this project's sources; adjust SNN_SRC if the project moves.
SNN_SRC ?= "/media/additional_space/ASIC_Design/SNN_based_network_packet_classifier"
SRC_URI = "file://${SNN_SRC}/sw/cv96/kmod/snn_fw.c \
           file://${SNN_SRC}/sw/cv96/snn_regs.h \
           file://${SNN_SRC}/sim/vectors/snn_fw.bin"
S = "${WORKDIR}/build"
do_configure:prepend() {
    mkdir -p ${S}/kmod
    cp ${SNN_SRC}/sw/cv96/kmod/snn_fw.c ${S}/kmod/
    cp ${SNN_SRC}/sw/cv96/snn_regs.h ${S}/
    printf 'obj-m := snn_fw.o\nall:\n\t$(MAKE) -C $(KERNEL_SRC) M=$(CURDIR) modules\nmodules_install:\n\t$(MAKE) -C $(KERNEL_SRC) M=$(CURDIR) modules_install\n' > ${S}/kmod/Makefile
}
MAKE_TARGETS = "-C ${S}/kmod"
MODULES_INSTALL_TARGET = "-C ${S}/kmod modules_install"
do_install:append() {
    install -d ${D}${nonarch_base_libdir}/firmware
    install -m 0644 ${SNN_SRC}/sim/vectors/snn_fw.bin ${D}${nonarch_base_libdir}/firmware/
}
FILES:${PN} += "${nonarch_base_libdir}/firmware/snn_fw.bin"
RPROVIDES:${PN} += "kernel-module-snn-fw"
