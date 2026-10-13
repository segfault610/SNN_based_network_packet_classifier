/* Register map of rtl/snn_lookaside_avmm.v (byte offsets from the slave base).
 * Chameleon96: LW H2F bridge 0xFF200000 + Platform Designer offset 0x10000. */
#ifndef SNN_REGS_H
#define SNN_REGS_H

#define SNN_PHYS_BASE      0xFF210000UL
#define SNN_SPAN           0x2000UL

#define SNN_W(word)        ((word) * 4u)
#define SNN_CTRL           SNN_W(0x000)
#define SNN_ST_SUBMITTED   SNN_W(0x020)
#define SNN_ST_REJECTED    SNN_W(0x021)
#define SNN_ST_MALICIOUS   SNN_W(0x022)
#define SNN_ST_LAST        SNN_W(0x023)
#define SNN_HDR(i)         SNN_W(0x400 + (i))      /* i = 0..31, 4 bytes each, LE */
#define SNN_SUBMIT         SNN_W(0x420)
#define SNN_VERDICT        SNN_W(0x421)
#define SNN_STATUS         SNN_W(0x422)
#define SNN_ID             SNN_W(0x423)

#define SNN_ID_VALUE       0x534E4E32u              /* "SNN2" */
#define SNN_HDR_MAX        128
#define SNN_STATUS_READY   (1u << 0)
#define SNN_STATUS_VAVAIL  (1u << 1)
#define SNN_V_VALID        (1u << 31)
#define SNN_V_MAL          (1u << 30)
#define SNN_V_CNT1(v)      (((v) >> 24) & 0xF)
#define SNN_V_CNT0(v)      (((v) >> 20) & 0xF)
#define SNN_V_TAG(v)       ((v) & 0xFF)
#define SNN_SUBMIT_WORD(len, n, tag) \
	(((unsigned)(tag) & 0xFF) << 24 | ((unsigned)(n) & 0xFF) << 16 | ((unsigned)(len) & 0xFFFF))

#endif
