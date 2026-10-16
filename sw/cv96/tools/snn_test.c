/*
 * snn_test - hardware test of the SNN accelerator on the Chameleon96 (or its RTL in co-simulation).
 *
 * Writes Ethernet frame headers straight into the accelerator's register window on the
 * lightweight HPS-to-FPGA bridge (physical 0xFF210000), starts a classification, reads the
 * verdict back and compares it with the golden model. The 600 frames, the weights and the
 * expected answers are the same files the RTL testbenches use (sim/vectors/), built in.
 *
 *   snn_test               run all tests C1..C10
 *   snn_test C3            run one test
 *   snn_test demo [ms]     replay normal traffic + the SYN flood slowly, one line per frame (watch LED1)
 *   snn_test stats         print ID, status and counters
 *
 * Your own traffic (snn_custom.c):
 *   snn_test craft list | craft <preset> [field=value ...]   build packets and classify them
 *   snn_test frame <hex bytes>                               classify one raw frame
 *   snn_test pcap <file.pcap> [max]                          classify a capture
 *   snn_test sniff [iface] [count]                           classify live received frames
 *
 * Feedback: text on the terminal, plus LED1 lighting for ~0.17 s per malicious verdict.
 * LED2 blinking every ~0.67 s = the design is alive. See docs/board_test_cv96.md.
 * Do not run while snn_fw.ko is loaded (both would use the accelerator).
 */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "hw.h"
#include "vectors.h"
#include "snn_custom.h"

/* ---------------------------------------------------------------- register map (word addresses) */
enum {
	R_CTRL = 0x000, R_TH1 = 0x001, R_TH2 = 0x002, R_TIMING = 0x003, R_B2 = 0x004, R_W2 = 0x010,
	R_SUBMITTED = 0x020, R_REJECTED = 0x021, R_MALICIOUS = 0x022, R_LAST = 0x023,
	R_HDR = 0x400, R_SUBMIT = 0x420, R_VERDICT = 0x421, R_STATUS = 0x422, R_ID = 0x423
};
#define ID_VALUE    0x534E4E32u      /* "SNN2" */
#define ST_READY    (1u << 0)
#define ST_VAVAIL   (1u << 1)
#define ST_COUNT(s) (((s) >> 8) & 0x1F)
#define POLL_MAX    200000

static int t_err;                    /* errors in the current test */
static int verbose_mismatch = 10;

static double now_s(void)
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec * 1e-9;
}

static void fail(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
static void fail(const char *fmt, ...)
{
	va_list ap;
	t_err++;
	if (t_err > verbose_mismatch) return;
	printf("    [ERR] ");
	va_start(ap, fmt); vprintf(fmt, ap); va_end(ap);
	printf("\n");
}

/* ---------------------------------------------------------------- primitives */
static int wait_ready(void)
{
	for (int i = 0; i < POLL_MAX; i++)
		if (hw_rd(R_STATUS) & ST_READY) return 1;
	return 0;
}

/* Write the header bytes (little endian, 4 per word) and SUBMIT {tag, n, true length}.
 * n = header-byte count put in SUBMIT; the hardware clips 0 -> 1 and > 128 -> 128. */
static void submit(const uint8_t *fr, unsigned len, unsigned n, unsigned tag)
{
	unsigned w, k, nb = n == 0 ? 1 : n > 128 ? 128 : n;
	if (nb > len) nb = len;
	for (w = 0; w < (nb + 3) / 4; w++) {
		uint32_t word = 0;
		for (k = 0; k < 4 && 4 * w + k < nb; k++) word |= (uint32_t)fr[4 * w + k] << (8 * k);
		hw_wr(R_HDR + w, word);
	}
	hw_wr(R_SUBMIT, ((tag & 0xFFu) << 24) | ((n & 0xFFu) << 16) | (len & 0xFFFFu));
}

static uint32_t wait_verdict(void)
{
	for (int i = 0; i < POLL_MAX; i++) {
		uint32_t v = hw_rd(R_VERDICT);            /* reading pops one verdict */
		if (v & V_VALID) return v;
	}
	return 0;
}

static uint32_t classify(const uint8_t *fr, unsigned len, unsigned tag)
{
	if (!wait_ready()) return 0;
	submit(fr, len, len > 128 ? 128 : len, tag);
	return wait_verdict();
}

uint32_t classify_len(const uint8_t *f, unsigned avail, unsigned len, unsigned tag)
{
	unsigned n = avail > 128 ? 128 : avail;
	if (!wait_ready()) return 0;
	submit(f, len, n, tag);
	return wait_verdict();
}

void drain(void)
{
	for (int i = 0; i < 64 && (hw_rd(R_STATUS) & ST_VAVAIL); i++) (void)hw_rd(R_VERDICT);
}

void load_weights(void)
{
	for (int i = 0; i < CFG_N; i++) hw_wr(cfg_addr[i], cfg_data[i]);
}

/* A 60-byte ARP request: neither a TCP SYN nor an ICMP echo. 32 of them empty the
 * accelerator's 32-frame SYN/ping rate window, so a replay starts from the same state as
 * the golden model (the window keeps its contents between runs; only a reboot clears it). */
void flush_rate_window(void)
{
	static const uint8_t arp[60] = {
		0xff,0xff,0xff,0xff,0xff,0xff, 0x02,0x00,0x00,0x00,0x00,0x01, 0x08,0x06,
		0x00,0x01, 0x08,0x00, 0x06, 0x04, 0x00,0x01,
		0x02,0x00,0x00,0x00,0x00,0x01, 192,168,1,10, 0,0,0,0,0,0, 192,168,1,1 };
	for (int i = 0; i < 32; i++) classify(arp, sizeof arp, 0xEE);
}

static const uint8_t *frame(int i) { return vec_bytes + vec_off[i]; }

/* replay frames [lo, hi] one at a time, compare every verdict with the golden model */
static int replay(int lo, int hi, int *tp, int *fp, int *tn, int *fn, double *secs)
{
	int n = 0;
	double t0 = now_s();
	for (int i = lo; i <= hi; i++) {
		uint32_t v = classify(frame(i), vec_len[i], i & 0xFF);
		if (!(v & V_VALID)) { fail("frame %d: no verdict (timeout)", i); continue; }
		if ((int)V_MAL(v) != exp_mal[i] || (int)V_C0(v) != exp_c0[i] || (int)V_C1(v) != exp_c1[i] ||
		    (int)V_TAG(v) != (i & 0xFF))
			fail("frame %d (%s): hw mal=%d cnt0=%d cnt1=%d tag=%d | golden mal=%d cnt0=%d cnt1=%d",
			     i, exp_kind[i], (int)V_MAL(v), (int)V_C0(v), (int)V_C1(v), (int)V_TAG(v), exp_mal[i], exp_c0[i], exp_c1[i]);
		if (tp) {
			int m = V_MAL(v), l = exp_lab[i];
			if (m && l) (*tp)++; else if (m) (*fp)++; else if (l) (*fn)++; else (*tn)++;
		}
		n++;
	}
	if (secs) *secs = now_s() - t0;
	return n;
}

/* ---------------------------------------------------------------- tests */
static void c1_identity(void)
{
	uint32_t id = hw_rd(R_ID), st;
	if (id != ID_VALUE) fail("ID register = 0x%08x, expected 0x534E4E32 (\"SNN2\")", (int)id);
	drain();
	st = hw_rd(R_STATUS);
	if (!(st & ST_READY)) fail("STATUS.ready = 0 while idle (STATUS=0x%x)", (int)st);
	if (st & ST_VAVAIL)   fail("verdicts still queued after draining (STATUS=0x%x)", (int)st);
	printf("    ID 0x%08x, STATUS 0x%x; since boot: submitted %u, rejected %u, malicious %u\n",
	       id, st, hw_rd(R_SUBMITTED), hw_rd(R_REJECTED), hw_rd(R_MALICIOUS));
}

static void c2_weights(void)
{
	int checked = 0;
	load_weights();
	for (int i = 0; i < CFG_N; i++) {
		uint32_t a = cfg_addr[i], d = cfg_data[i], r, want;
		if (a >= 0x100) continue;                 /* W1 is a write-only memory */
		r = hw_rd(a);
		want = (a == R_TIMING) ? (d & 0x3F) : (d & 0xFFFF);
		if (r != want) fail("register 0x%03x read 0x%08x, wrote 0x%08x", (int)a, (int)r, (int)d);
		checked++;
	}
	printf("    %d weight/threshold words written, %d readable registers checked\n", CFG_N, checked);
}

static int g_tp, g_fp, g_tn, g_fn;
static double g_secs;
static void c3_golden(void)
{
	uint32_t sub0;
	load_weights();
	drain();
	flush_rate_window();
	sub0 = hw_rd(R_SUBMITTED);
	g_tp = g_fp = g_tn = g_fn = 0;
	replay(0, VEC_N - 1, &g_tp, &g_fp, &g_tn, &g_fn, &g_secs);
	printf("    %d frames: malicious %d, benign %d | vs ground truth TP=%d FP=%d TN=%d FN=%d\n",
	       VEC_N, g_tp + g_fp, g_tn + g_fn, g_tp, g_fp, g_tn, g_fn);
	if (hw_rd(R_SUBMITTED) - sub0 != VEC_N) fail("submitted counter +%d, expected +%d", (int)(hw_rd(R_SUBMITTED) - sub0), VEC_N);
}

static void c4_counters(void)
{
	uint32_t sub0, mal0, rej0;
	int nmal = 0, i, last;
	flush_rate_window();
	sub0 = hw_rd(R_SUBMITTED); mal0 = hw_rd(R_MALICIOUS); rej0 = hw_rd(R_REJECTED);
	replay(0, 99, 0, 0, 0, 0, 0);
	for (i = 0; i < 100; i++) nmal += exp_mal[i];
	last = (exp_mal[99] << 8) | (exp_c1[99] << 4) | exp_c0[99];
	if (hw_rd(R_SUBMITTED) - sub0 != 100) fail("submitted +%d, expected +100", (int)(hw_rd(R_SUBMITTED) - sub0));
	if (hw_rd(R_MALICIOUS) - mal0 != (uint32_t)nmal) fail("malicious +%d, expected +%d", (int)(hw_rd(R_MALICIOUS) - mal0), nmal);
	if (hw_rd(R_REJECTED) != rej0) fail("rejected changed by %d, expected 0", (int)(hw_rd(R_REJECTED) - rej0));
	if (hw_rd(R_LAST) != (uint32_t)last) fail("last-verdict register 0x%03x, expected 0x%03x", (int)hw_rd(R_LAST), last);
	printf("    frames 0-99: submitted +100, malicious +%d, rejected +0, last verdict 0x%03x\n", nmal, last);
}

static void c5_status_irq(void)
{
	uint32_t st, v;
	drain();
	hw_wr(R_CTRL, 1);
	if ((hw_rd(R_CTRL) & 1) != 1) fail("CTRL.irq_en did not read back as 1");
	wait_ready();
	submit(frame(0), vec_len[0], vec_len[0] > 128 ? 128 : vec_len[0], 0x55);
	for (int i = 0; i < POLL_MAX && !((st = hw_rd(R_STATUS)) & ST_VAVAIL); i++) ;
	if (!(st & ST_VAVAIL) || ST_COUNT(st) != 1) fail("after one SUBMIT: STATUS=0x%x (want verdict-available, count 1)", (int)st);
	v = hw_rd(R_VERDICT);
	if (!(v & V_VALID) || V_TAG(v) != 0x55) fail("VERDICT=0x%08x, want valid with tag 0x55", (int)v);
	st = hw_rd(R_STATUS);
	if (st & ST_VAVAIL) fail("verdict-available still set after reading VERDICT (STATUS=0x%x)", (int)st);
	v = hw_rd(R_VERDICT);
	if (v & V_VALID) fail("reading an empty queue returned a valid verdict 0x%08x", (int)v);
	hw_wr(R_CTRL, 0);
	printf("    irq_en set/cleared; STATUS goes 'verdict available, 1 queued' -> empty after the read\n");
}

static void c6_sizes(void)
{
	static uint8_t big[1518];
	const uint8_t *f0 = frame(0);
	uint32_t rej0 = hw_rd(R_REJECTED), v;
	struct { const char *what; unsigned len, n; } t[] = {   /* len = true frame length, n = header bytes */
		{ "8-byte runt (shorter than an Ethernet header)", 8, 8 },
		{ "SUBMIT with 0 header bytes (treated as 1)", 60, 0 },
		{ "SUBMIT with 200 header bytes (clipped to 128)", 1518, 200 },
		{ "1518-byte maximum frame, 128-byte header", 1518, 128 },
	};
	memcpy(big, f0, vec_len[0]);
	for (unsigned i = 0; i < sizeof t / sizeof t[0]; i++) {
		if (!wait_ready()) { fail("not ready before case %d", (int)i); continue; }
		submit(big, t[i].len, t[i].n, 0x60 + i);        /* n unclipped on purpose */
		v = wait_verdict();
		if (!(v & V_VALID) || V_TAG(v) != 0x60 + i) fail("case %d: VERDICT=0x%08x, want valid with tag 0x%02x", (int)i, (int)v, 0x60 + (int)i);
		else printf("    %-48s -> verdict returned (%s)\n", t[i].what, V_MAL(v) ? "malicious" : "benign");
	}
	if (hw_rd(R_REJECTED) != rej0) fail("rejected counter changed by %d", (int)(hw_rd(R_REJECTED) - rej0));
	if (hw_rd(R_STATUS) & ST_VAVAIL) fail("extra verdicts queued after the size cases");
}

static void c7_failsafe(void)
{
	int flagged = 0;
	for (int h = 0; h < 16; h++) hw_wr(R_W2 + h, 0);
	hw_wr(R_B2, 0);
	flush_rate_window();
	for (int i = 47; i <= 147; i++) {                 /* the SYN flood */
		uint32_t v = classify(frame(i), vec_len[i], i & 0xFF);
		if (!(v & V_VALID)) fail("frame %d: no verdict", i);
		flagged += V_MAL(v);
	}
	if (flagged) fail("%d SYN-flood frames flagged with zero output weights, expected 0", flagged);
	load_weights();
	printf("    output weights = 0 (as after power-up): 101 SYN-flood frames -> %d flagged (fail-safe: all pass)\n", flagged);
}

static void c8_pipelined(void)
{
	/* keep several frames in flight: submit as soon as the accelerator is ready, read verdicts later */
	const int N = 120, BATCH = 12;
	int next_rd = 0;
	flush_rate_window();
	for (int i = 0; i < N; i++) {
		if (!wait_ready()) { fail("not ready at frame %d", i); break; }
		submit(frame(i), vec_len[i], vec_len[i] > 128 ? 128 : vec_len[i], i & 0xFF);
		if (i - next_rd + 1 >= BATCH || i == N - 1) {
			while (next_rd <= i) {
				uint32_t v = wait_verdict();
				int k = next_rd++;
				if (!(v & V_VALID) || (int)V_MAL(v) != exp_mal[k] || (int)V_C0(v) != exp_c0[k] ||
				    (int)V_C1(v) != exp_c1[k] || (int)V_TAG(v) != (k & 0xFF))
					fail("frame %d (batched): hw 0x%08x, golden mal=%d", k, (int)v, exp_mal[k]);
			}
		}
	}
	printf("    %d frames, up to %d in flight before reading verdicts: order and values bit-exact\n", N, BATCH);
}

static void c9_overload(void)
{
	/* submit 40 frames without waiting for ready and without reading verdicts */
	const int N = 40;
	uint32_t sub0, rej0, acc, rej;
	int got = 0, last_tag = -1, order_ok = 1;
	drain();
	sub0 = hw_rd(R_SUBMITTED); rej0 = hw_rd(R_REJECTED);
	for (int i = 0; i < N; i++) submit(frame(i), vec_len[i], vec_len[i] > 128 ? 128 : vec_len[i], i);
	for (int k = 0; k < 5000; k++) (void)hw_rd(R_STATUS);           /* let the pipeline settle */
	acc = hw_rd(R_SUBMITTED) - sub0; rej = hw_rd(R_REJECTED) - rej0;
	for (;;) {
		uint32_t v = hw_rd(R_VERDICT);
		if (!(v & V_VALID)) {
			int still = 0;
			for (int k = 0; k < 2000; k++) if (hw_rd(R_STATUS) & ST_VAVAIL) { still = 1; break; }
			if (!still) break;
			continue;
		}
		if ((int)V_TAG(v) <= last_tag) order_ok = 0;
		last_tag = V_TAG(v); got++;
	}
	if (acc + rej != (uint32_t)N) fail("accepted %d + rejected %d != %d submitted", (int)acc, (int)rej, N);
	if (rej == 0) fail("no SUBMIT was rejected under overload (accepted %d)", (int)acc);
	if (got != (int)acc) fail("%d verdicts read back, %d frames accepted", got, (int)acc);
	if (!order_ok) fail("verdicts out of order");
	printf("    40 SUBMITs without waiting: %u accepted, %u rejected (counted), %d verdicts back in order\n", acc, rej, got);
}

static void c10_recovery(void)
{
	drain();
	load_weights();
	flush_rate_window();
	replay(0, 59, 0, 0, 0, 0, 0);
	printf("    after the overload: queue drained, window flushed, frames 0-59 bit-exact again\n");
}

static void demo(int ms)
{
	const int lo = 0, hi = 140;
	load_weights();
	drain();
	flush_rate_window();
	printf("Replaying frames %d-%d: normal traffic, then the SYN flood starts at frame 47.\n", lo, hi);
	printf("Watch LED1: it lights for each frame judged malicious.\n\n");
	for (int i = lo; i <= hi; i++) {
		uint32_t v = classify(frame(i), vec_len[i], i & 0xFF);
		printf("frame %3d  %-10s  -> %-9s  (benign neuron %2u spikes, malicious neuron %2u)%s\n", i, exp_kind[i],
		       V_MAL(v) ? "MALICIOUS" : "benign", V_C0(v), V_C1(v),
		       (int)V_MAL(v) != exp_mal[i] ? "  <-- differs from golden model!" : "");
		fflush(stdout);
		if (ms > 0) usleep(ms * 1000);
	}
}

static void stats(void)
{
	uint32_t st = hw_rd(R_STATUS);
	printf("ID 0x%08x  STATUS 0x%x (ready %u, verdicts queued %u)  CTRL 0x%x\n", hw_rd(R_ID), st,
	       st & ST_READY, ST_COUNT(st), hw_rd(R_CTRL));
	printf("TH1 %u  TH2 %u  TIMING 0x%x  B2 0x%04x\n", hw_rd(R_TH1), hw_rd(R_TH2), hw_rd(R_TIMING), hw_rd(R_B2));
	printf("submitted %u  rejected %u  malicious %u  last 0x%03x\n", hw_rd(R_SUBMITTED), hw_rd(R_REJECTED),
	       hw_rd(R_MALICIOUS), hw_rd(R_LAST));
}

/* ---------------------------------------------------------------- main */
static const struct { const char *id, *name; void (*fn)(void); } tests[] = {
	{ "C1",  "identity and idle state (T1)",                   c1_identity },
	{ "C2",  "load weights, read back (T2)",                   c2_weights },
	{ "C3",  "600 golden frames, bit-exact (T3)",              c3_golden },
	{ "C4",  "hardware counters (T3 counter checks)",          c4_counters },
	{ "C5",  "status bits and verdict-ready interrupt flag",   c5_status_irq },
	{ "C6",  "odd sizes: runt, 0/200-byte header, 1518 B (T7)", c6_sizes },
	{ "C7",  "fail-safe with no weights loaded",               c7_failsafe },
	{ "C8",  "several frames in flight (T8)",                  c8_pipelined },
	{ "C9",  "overload: submit without waiting (T9)",          c9_overload },
	{ "C10", "recovery after overload (T10)",                  c10_recovery },
};

int main(int argc, char **argv)
{
	unsigned long base = getenv("SNN_BASE") ? strtoul(getenv("SNN_BASE"), NULL, 0) : 0xFF210000UL;
	const char *only = argc > 1 ? argv[1] : NULL;
	int failed = 0, ran = 0;

	if (access("/proc/snn_fw", F_OK) == 0) {
		fprintf(stderr, "snn_fw.ko is loaded and uses the accelerator: run 'rmmod snn_fw' first\n");
		return 2;
	}
	if (hw_open(base)) return 1;
	if (hw_rd(R_ID) != ID_VALUE) {
		fprintf(stderr, "no SNN accelerator at 0x%lx (ID reads 0x%08x).\n"
		        "Is cv96_snn.rbf loaded and the lwhps2fpga bridge enabled?\n", base, hw_rd(R_ID));
		return 1;
	}
	printf("SNN accelerator found at 0x%lx (%s)\n", base, hw_name());

	if (only && !strcmp(only, "stats")) { stats(); return 0; }
	if (only && !strcmp(only, "demo"))  { demo(argc > 2 ? atoi(argv[2]) : 150); return 0; }
	if (only && (!strcmp(only, "craft") || !strcmp(only, "frame") || !strcmp(only, "pcap") || !strcmp(only, "sniff")))
		return custom_main(argc - 1, argv + 1);

	for (unsigned i = 0; i < sizeof tests / sizeof tests[0]; i++) {
		if (only && strcasecmp(only, tests[i].id)) continue;
		t_err = 0;
		printf("[%s] %s\n", tests[i].id, tests[i].name);
		tests[i].fn();
		printf("  %s %s\n", t_err ? "FAIL" : "PASS", tests[i].id);
		failed += t_err != 0; ran++;
	}
	if (!ran) {
		fprintf(stderr, "usage: %s [C1..C10 | demo [ms] | stats | craft list | craft <preset> [field=value ...] |\n"
		        "        frame <hex> | pcap <file> [max] | sniff [iface] [count]]   (see docs/custom_traffic_cv96.md)\n", argv[0]);
		return 2;
	}
	if (!only || !strcasecmp(only, "C3"))
		printf("\nthroughput (C3): %.0f frames/s, %.1f us per frame incl. bus transfers\n",
		       VEC_N / g_secs, 1e6 * g_secs / VEC_N);
	printf("============================================================\n");
	printf(" RESULT: %s (%d of %d tests passed)\n", failed ? "FAIL" : "PASS", ran - failed, ran);
	printf("============================================================\n");
	return failed != 0;
}
