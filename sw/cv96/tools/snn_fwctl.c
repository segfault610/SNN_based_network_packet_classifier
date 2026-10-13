/*
 * snn_fwctl - user-space control / on-board self-test for the SNN accelerator.
 *
 *   snn_fwctl id
 *   snn_fwctl load     cfg.txt                  # "<addr_hex> <data_hex>" per line
 *   snn_fwctl stats
 *   snn_fwctl selftest frames.txt expected.txt  # bit-exact check vs golden model
 *
 * Uses /dev/mem (root). Do not run selftest while snn_fw.ko is loaded.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <sys/mman.h>
#include "snn_regs.h"

static volatile uint8_t *regs;

static inline uint32_t rd(uint32_t off)           { return *(volatile uint32_t *)(regs + off); }
static inline void     wr(uint32_t off, uint32_t v){ *(volatile uint32_t *)(regs + off) = v; }

static int map(unsigned long base)
{
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) { perror("/dev/mem"); return -1; }
	void *p = mmap(NULL, SNN_SPAN, PROT_READ | PROT_WRITE, MAP_SHARED, fd, base);
	close(fd);
	if (p == MAP_FAILED) { perror("mmap"); return -1; }
	regs = p;
	return 0;
}

static double now_us(void)
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}

static int load_cfg(const char *path)
{
	FILE *f = fopen(path, "r");
	unsigned a, d, n = 0;
	if (!f) { perror(path); return 1; }
	while (fscanf(f, "%x %x", &a, &d) == 2) { wr(SNN_W(a & 0x3FF), d); n++; }
	fclose(f);
	printf("loaded %u config words\n", n);
	return 0;
}

static uint32_t classify(const uint8_t *fr, unsigned len, uint8_t tag)
{
	unsigned n = len > SNN_HDR_MAX ? SNN_HDR_MAX : len, w, k, i;
	uint32_t v = 0;
	for (i = 0; i < 1000000 && !(rd(SNN_STATUS) & SNN_STATUS_READY); i++) ;
	for (w = 0; w < (n + 3) / 4; w++) {
		uint32_t word = 0;
		for (k = 0; k < 4 && 4 * w + k < n; k++) word |= (uint32_t)fr[4 * w + k] << (8 * k);
		wr(SNN_HDR(w), word);
	}
	wr(SNN_SUBMIT, SNN_SUBMIT_WORD(len, n, tag));
	for (i = 0; i < 1000000; i++) { v = rd(SNN_VERDICT); if (v & SNN_V_VALID) break; }
	return v;
}

static int selftest(const char *frames, const char *expected)
{
	FILE *ff = fopen(frames, "r"), *fe = fopen(expected, "r");
	static uint8_t fr[65536];
	unsigned len, b, c0, c1, mal, lab, n = 0, err = 0, tp = 0, fp = 0, tn = 0, fn = 0;
	char spk[32], kind[64];
	double t = 0;
	if (!ff || !fe) { perror("open vectors"); return 1; }
	while (fscanf(ff, "%u", &len) == 1) {
		for (unsigned i = 0; i < len; i++) { if (fscanf(ff, "%x", &b) != 1) return 1; fr[i] = b; }
		if (fscanf(fe, "%31s %u %u %u %u %63s", spk, &c0, &c1, &mal, &lab, kind) != 6) break;
		double t0 = now_us();
		uint32_t v = classify(fr, len, n & 0xFF);
		t += now_us() - t0;
		unsigned hm = !!(v & SNN_V_MAL);
		if (!(v & SNN_V_VALID) || hm != mal || SNN_V_CNT0(v) != c0 || SNN_V_CNT1(v) != c1 || SNN_V_TAG(v) != (n & 0xFF)) {
			if (err++ < 10)
				printf("MISMATCH frame %u (%s): hw v=%08x exp mal=%u c0=%u c1=%u\n", n, kind, v, mal, c0, c1);
		}
		if (hm && lab) tp++; else if (hm) fp++; else if (lab) fn++; else tn++;
		n++;
	}
	printf("selftest: %u frames, %u mismatches, TP=%u FP=%u TN=%u FN=%u, avg %.2f us/frame (%.0f frames/s)\n",
	       n, err, tp, fp, tn, fn, t / n, n / (t / 1e6));
	printf("RESULT: %s\n", err ? "FAIL" : "PASS (FPGA bit-exact with golden model)");
	return err != 0;
}

int main(int argc, char **argv)
{
	unsigned long base = getenv("SNN_BASE") ? strtoul(getenv("SNN_BASE"), NULL, 0) : SNN_PHYS_BASE;
	if (argc < 2) {
		fprintf(stderr, "usage: %s id | load cfg.txt | stats | selftest frames.txt expected.txt\n", argv[0]);
		return 2;
	}
	if (map(base)) return 1;
	uint32_t id = rd(SNN_ID);
	if (id != SNN_ID_VALUE) {
		fprintf(stderr, "no SNN accelerator at %#lx (read %#x). RBF loaded? LW bridge enabled?\n", base, id);
		return 1;
	}
	if (!strcmp(argv[1], "id"))       { printf("SNN accelerator ID %#x at %#lx\n", id, base); return 0; }
	if (!strcmp(argv[1], "load") && argc > 2) return load_cfg(argv[2]);
	if (!strcmp(argv[1], "stats")) {
		printf("submitted %u\nrejected  %u\nmalicious %u\nTH1 %u TH2 %u timing %#x\n",
		       rd(SNN_ST_SUBMITTED), rd(SNN_ST_REJECTED), rd(SNN_ST_MALICIOUS),
		       rd(SNN_W(1)), rd(SNN_W(2)), rd(SNN_W(3)));
		return 0;
	}
	if (!strcmp(argv[1], "selftest") && argc > 3) return selftest(argv[2], argv[3]);
	fprintf(stderr, "bad command\n");
	return 2;
}
