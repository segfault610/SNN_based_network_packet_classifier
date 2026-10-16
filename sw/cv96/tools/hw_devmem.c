/* Board back end: map the accelerator through /dev/mem (needs root).
 * Chameleon96: LW H2F bridge at 0xFF200000 + Platform Designer offset 0x10000 = 0xFF210000. */
#include <fcntl.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>
#include "hw.h"

#define SPAN 0x2000u                    /* 2048 words: config, header window, control */
static volatile uint32_t *regs;

int hw_open(unsigned long base)
{
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) { perror("open /dev/mem (run as root)"); return -1; }
	void *p = mmap(NULL, SPAN, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (off_t)base);
	close(fd);
	if (p == MAP_FAILED) { perror("mmap"); return -1; }
	regs = (volatile uint32_t *)p;
	return 0;
}
uint32_t    hw_rd(uint32_t w)             { return regs[w]; }
void        hw_wr(uint32_t w, uint32_t v) { regs[w] = v; }
const char *hw_name(void)                 { return "FPGA via /dev/mem"; }
