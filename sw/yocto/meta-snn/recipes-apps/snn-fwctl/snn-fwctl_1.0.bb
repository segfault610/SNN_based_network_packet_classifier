SUMMARY = "SNN accelerator control / on-board self-test tool + golden vectors"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"
SNN_SRC ?= "/media/additional_space/ASIC_Design/SNN_based_network_packet_classifier"
S = "${WORKDIR}/build"
do_compile() {
    mkdir -p ${S}
    ${CC} ${CFLAGS} ${LDFLAGS} -I${SNN_SRC}/sw -o ${S}/snn_fwctl ${SNN_SRC}/sw/tools/snn_fwctl.c
}
do_install() {
    install -d ${D}${bindir} ${D}${datadir}/snn
    install -m 0755 ${S}/snn_fwctl ${D}${bindir}/
    install -m 0644 ${SNN_SRC}/sim/vectors/cfg.txt ${SNN_SRC}/sim/vectors/frames.txt \
                    ${SNN_SRC}/sim/vectors/expected.txt ${D}${datadir}/snn/
}
FILES:${PN} += "${datadir}/snn"
