/* Register access for snn_test. Two back ends with the same interface:
 *   hw_devmem.c          the real board: /dev/mem mapping of the LW HPS-to-FPGA bridge
 *   cosim/hw_verilator.cpp  the laptop: the same RTL (snn_lookaside_avmm) compiled with Verilator
 * Addresses are WORD addresses as in rtl/snn_lookaside_avmm.v (byte offset = 4 * word). */
#ifndef SNN_HW_H
#define SNN_HW_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
int         hw_open(unsigned long phys_base);   /* 0 = ok */
uint32_t    hw_rd(uint32_t word);
void        hw_wr(uint32_t word, uint32_t value);
const char *hw_name(void);
#ifdef __cplusplus
}
#endif
#endif
