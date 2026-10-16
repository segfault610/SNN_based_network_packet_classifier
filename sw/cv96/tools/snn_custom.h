/* Shared between snn_test.c (register primitives, built-in tests) and snn_custom.c (your own traffic). */
#ifndef SNN_CUSTOM_H
#define SNN_CUSTOM_H
#include <stdint.h>

#define V_VALID     (1u << 31)
#define V_MAL(v)    (((v) >> 30) & 1)
#define V_C1(v)     (((v) >> 24) & 0xF)
#define V_C0(v)     (((v) >> 20) & 0xF)
#define V_TAG(v)    ((v) & 0xFF)

/* classify one frame: 'avail' bytes present in f (the first <= 128 are sent), 'len' = true frame length */
uint32_t classify_len(const uint8_t *f, unsigned avail, unsigned len, unsigned tag);
void     load_weights(void);         /* the trained network (cfg.txt, built in) */
void     drain(void);                /* discard verdicts nobody read */
void     flush_rate_window(void);    /* 32 neutral frames: empty the SYN/ping memory */
int      custom_main(int argc, char **argv);   /* craft | frame | pcap | sniff */
#endif
