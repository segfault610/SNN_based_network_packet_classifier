/*
 * snn_custom.c - classify YOUR traffic with the SNN accelerator (part of snn_test).
 *
 *   snn_test craft list                         list the packet presets
 *   snn_test craft <preset> [field=value ...]   build packets, classify them, print header + verdict
 *   snn_test frame <hex bytes ...> | -          classify one raw Ethernet frame given as hex (or read hex from stdin)
 *   snn_test pcap <file.pcap> [max]             classify every frame of a capture (tcpdump -w, classic pcap)
 *   snn_test sniff [iface] [count]              classify live received frames from a network interface (default wlan0)
 *
 * Extra words anywhere: 'hex' also prints each frame's bytes; 'noflush' keeps the accelerator's
 * 32-frame SYN/ping memory instead of emptying it first.
 *
 * What the hardware looks at: the first <= 128 bytes of each frame (Ethernet type, IPv4 header,
 * TCP/UDP/ICMP header) plus the true frame length, plus how many SYNs / pings it saw in the last
 * 32 frames. Never the payload content. The header summary printed next to each verdict is decoded
 * here in software only so you can see what was judged.
 */
#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <linux/if_packet.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
#include "snn_custom.h"

static int opt_hex;
static unsigned n_frames, n_mal, tag_ctr;

/* ---------------------------------------------------------------- header decoding (display only) */
static unsigned b8(const uint8_t *f, unsigned len, unsigned i) { return i < len ? f[i] : 0; }
static unsigned b16(const uint8_t *f, unsigned len, unsigned i) { return (b8(f, len, i) << 8) | b8(f, len, i + 1); }

static void describe(const uint8_t *f, unsigned avail, unsigned len, char *out, size_t n)
{
	unsigned l3 = 14, et = b16(f, avail, 12);
	if (et == 0x8100) { l3 = 18; et = b16(f, avail, 16); }
	if (et == 0x0806) { snprintf(out, n, "ARP %s, %u B", b16(f, avail, l3 + 6) == 1 ? "request" : "reply", len); return; }
	if (et == 0x86DD) { snprintf(out, n, "IPv6, %u B", len); return; }
	if (et != 0x0800) { snprintf(out, n, "EtherType 0x%04x, %u B", et, len); return; }
	unsigned ihl = b8(f, avail, l3) & 0xF, ttl = b8(f, avail, l3 + 8), proto = b8(f, avail, l3 + 9);
	unsigned ff = b16(f, avail, l3 + 6), l4 = l3 + 4 * ihl;
	char src[16], dst[16], fl[8] = "", extra[64] = "";
	snprintf(src, sizeof src, "%u.%u.%u.%u", b8(f, avail, l3 + 12), b8(f, avail, l3 + 13), b8(f, avail, l3 + 14), b8(f, avail, l3 + 15));
	snprintf(dst, sizeof dst, "%u.%u.%u.%u", b8(f, avail, l3 + 16), b8(f, avail, l3 + 17), b8(f, avail, l3 + 18), b8(f, avail, l3 + 19));
	if (ff & 0x2000 || ff & 0x1FFF) snprintf(extra, sizeof extra, " frag(MF=%u off=%u)", (ff >> 13) & 1, ff & 0x1FFF);
	if (ihl != 5) { size_t k = strlen(extra); snprintf(extra + k, sizeof extra - k, " ihl=%u", ihl); }
	if (proto == 6) {
		unsigned fb = b8(f, avail, l4 + 13), doff = b8(f, avail, l4 + 12) >> 4, k = 0;
		const char *letters = "FSRPAU";
		for (int i = 0; i < 6; i++) if (fb >> i & 1) fl[k++] = letters[i];
		fl[k] = 0;
		snprintf(out, n, "TCP %s:%u > %s:%u [%s] ttl=%u win=%u opts=%uB %uB%s", src, b16(f, avail, l4), dst,
		         b16(f, avail, l4 + 2), k ? fl : "none", ttl, b16(f, avail, l4 + 14), doff > 5 ? (doff - 5) * 4 : 0, len, extra);
	} else if (proto == 17) {
		snprintf(out, n, "UDP %s:%u > %s:%u ttl=%u %uB%s", src, b16(f, avail, l4), dst, b16(f, avail, l4 + 2), ttl, len, extra);
	} else if (proto == 1) {
		unsigned ty = b8(f, avail, l4);
		snprintf(out, n, "ICMP %s > %s %s ttl=%u %uB%s", src, dst,
		         ty == 8 ? "echo-request" : ty == 0 ? "echo-reply" : ty == 3 ? "unreachable" : "other", ttl, len, extra);
	} else {
		snprintf(out, n, "IPv4 proto %u %s > %s ttl=%u %uB%s", proto, src, dst, ttl, len, extra);
	}
}

/* classify one frame (avail bytes present, true length len) and print one line */
static void judge(const uint8_t *f, unsigned avail, unsigned len, const char *label)
{
	char d[200];
	uint32_t v = classify_len(f, avail, len, tag_ctr++ & 0xFF);
	describe(f, avail, len, d, sizeof d);
	n_frames++;
	if (!(v & V_VALID)) { printf("%4u  no verdict (timeout)          %s\n", n_frames, d); return; }
	n_mal += V_MAL(v);
	printf("%4u  %-9s (%u:%u)  %s%s%s\n", n_frames, V_MAL(v) ? "MALICIOUS" : "benign", V_C0(v), V_C1(v), d,
	       label ? "  " : "", label ? label : "");
	if (opt_hex) {
		printf("      hex:");
		for (unsigned i = 0; i < avail; i++) printf(" %02x", f[i]);
		printf("\n");
	}
	fflush(stdout);
}

static void summary(void)
{
	printf("---- %u frames: %u malicious, %u benign\n", n_frames, n_mal, n_frames - n_mal);
}

/* ---------------------------------------------------------------- packet builder */
typedef struct {
	const char *name, *what;
	int proto;               /* 6 TCP, 17 UDP, 1 ICMP, 0x806 ARP */
	unsigned flags;          /* TCP flags */
	int ttl, sport, dport, win, opts, payload, df, mf, foff, ihl, icmp, count, inc;
	uint8_t src[4], dst[4];
	int malicious;           /* what the preset is meant to be (for the printout only) */
	int l4cut;               /* >0: cut the TCP/UDP/ICMP header to this many bytes (tiny fragments) */
} pkt_t;

static const pkt_t presets[] = {
	/*  name        what                                                     proto flags ttl  sport  dport win    opt pay df mf foff ihl icmp cnt inc  src            dst           mal */
	{ "syn",        "client opens a connection (with TCP options, TTL 64)", 6, 0x02, 64, 51234,   443, 64240, 12,  0, 1, 0, 0, 5, 0,  1, 0, {192,168,1,23}, {93,184,216,34}, 0, 0 },
	{ "ack",        "acknowledgement inside a connection",                  6, 0x10, 64, 51234,   443, 64240, 12,  0, 1, 0, 0, 5, 0,  1, 0, {192,168,1,23}, {93,184,216,34}, 0, 0 },
	{ "data",       "web data (PSH+ACK, 300 B payload)",                    6, 0x18, 64, 51234,   443, 64240, 12,300, 1, 0, 0, 5, 0,  1, 0, {192,168,1,23}, {93,184,216,34}, 0, 0 },
	{ "fin",        "polite connection close (FIN+ACK)",                    6, 0x11, 64, 51234,   443, 64240,  0,  0, 1, 0, 0, 5, 0,  1, 0, {192,168,1,23}, {93,184,216,34}, 0, 0 },
	{ "ping",       "ping request, 56 B",                                   1, 0,    64,     0,     0,     0,  0, 56, 0, 0, 0, 5, 8,  1, 0, {192,168,1,23}, {8,8,8,8},       0, 0 },
	{ "dns",        "DNS query",                                           17, 0,    64, 53111,    53,     0,  0, 32, 0, 0, 0, 5, 0,  1, 0, {192,168,1,23}, {8,8,8,8},       0, 0 },
	{ "arp",        "ARP request",                                      0x806, 0,     0,     0,     0,     0,  0,  0, 0, 0, 0, 5, 0,  1, 0, {192,168,1,23}, {192,168,1,1},   0, 0 },
	{ "synflood",   "SYN flood: bare SYNs, no options, odd TTL (x40)",      6, 0x02, 200, 4000,    80,   512,  0,  0, 0, 0, 0, 5, 0, 40, 0, {203,0,113,9},  {192,168,1,10},  1, 0 },
	{ "synscan",    "SYN port scan, ports 1-25",                            6, 0x02, 45, 41000,     1,  1024,  0,  0, 0, 0, 0, 5, 0, 25, 1, {198,51,100,7}, {192,168,1,10},  1, 0 },
	{ "xmas",       "Xmas scan (FIN+PSH+URG), ports 1-25",                  6, 0x29, 45, 41000,     1,  1024,  0,  0, 0, 0, 0, 5, 0, 25, 1, {198,51,100,7}, {192,168,1,10},  1, 0 },
	{ "null",       "NULL scan (no flags), ports 1-25",                     6, 0x00, 45, 41000,     1,  1024,  0,  0, 0, 0, 0, 5, 0, 25, 1, {198,51,100,7}, {192,168,1,10},  1, 0 },
	{ "finscan",    "FIN scan, ports 1-25",                                 6, 0x01, 45, 41000,     1,  1024,  0,  0, 0, 0, 0, 5, 0, 25, 1, {198,51,100,7}, {192,168,1,10},  1, 0 },
	{ "ackscan",    "ACK scan (maps firewall rules), ports 1-25",           6, 0x10, 45, 41000,     1,  1024,  0,  0, 0, 0, 0, 5, 0, 25, 1, {198,51,100,7}, {192,168,1,10},  1, 0 },
	{ "udpscan",    "UDP scan, ports 1-25",                                17, 0,    45, 41000,     1,     0,  0,  0, 0, 0, 0, 5, 0, 25, 1, {198,51,100,7}, {192,168,1,10},  1, 0 },
	{ "port0",      "SYN to port 0 (invalid port)",                         6, 0x02, 64, 30000,     0,  1024,  0,  0, 1, 0, 0, 5, 0,  3, 0, {198,51,100,7}, {192,168,1,10},  1, 0 },
	{ "land",       "land attack: source = destination",                    6, 0x02, 64,    80,    80,  1024,  0,  0, 1, 0, 0, 5, 0,  3, 0, {192,168,1,10}, {192,168,1,10},  1, 0 },
	{ "pingflood",  "ping flood: 1000 B pings, odd TTL (x40)",              1, 0,   200,     0,     0,     0,  0,1000,0, 0, 0, 5, 8, 40, 0, {203,0,113,9},  {192,168,1,10},  1, 0 },
	{ "smurf",      "smurf: ping to a broadcast address",                   1, 0,    90,     0,     0,     0,  0, 56, 0, 0, 0, 5, 8,  5, 0, {192,168,1,10}, {192,168,1,255}, 1, 0 },
	{ "bogon",      "SYN from an impossible source (127.x)",                6, 0x02, 64, 30000,    22,  1024,  0,  0, 1, 0, 0, 5, 0,  3, 0, {127,4,5,6},    {192,168,1,10},  1, 0 },
	{ "lowttl",     "data with TTL 1 (IDS evasion trick)",                  6, 0x18,  1, 30000,    80, 64240,  0, 40, 1, 0, 0, 5, 0,  3, 0, {198,51,100,7}, {192,168,1,10},  1, 0 },
	{ "tinyfrag",   "tiny first fragment (hides the TCP header)",           6, 0x02, 64, 30000,    80,  1024,  0,  0, 0, 1, 0, 5, 0,  3, 0, {198,51,100,7}, {192,168,1,10},  1, 8 },
	{ "malformed",  "IPv4 header length 3 (impossible)",                    6, 0x02, 64, 30000,    80,  1024,  0,  0, 1, 0, 0, 3, 0,  3, 0, {198,51,100,7}, {192,168,1,10},  1, 0 },
};
#define N_PRESETS (sizeof presets / sizeof presets[0])

static uint16_t ip_csum(const uint8_t *h, unsigned n)
{
	uint32_t s = 0;
	for (unsigned i = 0; i + 1 < n; i += 2) s += (h[i] << 8) | h[i + 1];
	while (s >> 16) s = (s & 0xFFFF) + (s >> 16);
	return (uint16_t)~s;
}

static unsigned build(const pkt_t *p, int k, uint8_t *f)
{
	static const uint8_t dmac[6] = {0x02,0x00,0x5e,0x10,0x00,0x01}, smac[6] = {0x02,0x00,0x5e,0x20,0x00,0x02};
	unsigned n = 0, i;
	memcpy(f, dmac, 6); memcpy(f + 6, smac, 6); n = 12;
	if (p->proto == 0x806) {
		f[n++] = 0x08; f[n++] = 0x06;
		const uint8_t a[8] = {0, 1, 8, 0, 6, 4, 0, 1};
		memcpy(f + n, a, 8); n += 8;
		memcpy(f + n, smac, 6); n += 6; memcpy(f + n, p->src, 4); n += 4;
		memset(f + n, 0, 6); n += 6; memcpy(f + n, p->dst, 4); n += 4;
	} else {
		f[n++] = 0x08; f[n++] = 0x00;
		unsigned ip = n, ihl = (unsigned)p->ihl, hl = ihl >= 5 ? ihl * 4 : 20;
		unsigned l4 = ip + hl, dport = (unsigned)(p->dport + (p->inc ? k : 0)) & 0xFFFF, l4len;
		memset(f + ip, 0, hl);
		if (p->proto == 6) {
			unsigned ob = (unsigned)p->opts & ~3u;
			if (ob > 40) ob = 40;
			memset(f + l4, 0, 20 + ob);
			f[l4] = p->sport >> 8; f[l4 + 1] = p->sport; f[l4 + 2] = dport >> 8; f[l4 + 3] = dport;
			f[l4 + 4] = 0x12; f[l4 + 5] = 0x34; f[l4 + 6] = k; f[l4 + 7] = 0x01;
			f[l4 + 12] = (uint8_t)((5 + ob / 4) << 4); f[l4 + 13] = p->flags;
			f[l4 + 14] = p->win >> 8; f[l4 + 15] = p->win;
			if (ob) { f[l4 + 20] = 2; f[l4 + 21] = 4; f[l4 + 22] = 0x05; f[l4 + 23] = 0xb4;      /* MSS 1460 */
			          for (i = 4; i < ob; i++) f[l4 + 20 + i] = 1; }                        /* NOPs */
			l4len = 20 + ob;
		} else if (p->proto == 17) {
			memset(f + l4, 0, 8);
			f[l4] = p->sport >> 8; f[l4 + 1] = p->sport; f[l4 + 2] = dport >> 8; f[l4 + 3] = dport;
			f[l4 + 4] = (8 + p->payload) >> 8; f[l4 + 5] = 8 + p->payload;
			l4len = 8;
		} else {
			memset(f + l4, 0, 8);
			f[l4] = p->icmp; f[l4 + 6] = 0; f[l4 + 7] = k;
			l4len = 8;
		}
		if (p->l4cut > 0 && (unsigned)p->l4cut < l4len) l4len = (unsigned)p->l4cut;
		for (i = 0; i < (unsigned)p->payload && l4 + l4len + i < 1514; i++) f[l4 + l4len + i] = (uint8_t)(0x41 + i % 26);
		unsigned tot = hl + l4len + i;
		f[ip] = 0x40 | (ihl & 0xF);
		f[ip + 2] = tot >> 8; f[ip + 3] = tot;
		f[ip + 4] = 0x1c; f[ip + 5] = k;
		unsigned ff = (p->df ? 0x4000 : 0) | (p->mf ? 0x2000 : 0) | (p->foff & 0x1FFF);
		f[ip + 6] = ff >> 8; f[ip + 7] = ff;
		f[ip + 8] = p->ttl; f[ip + 9] = p->proto;
		memcpy(f + ip + 12, p->src, 4); memcpy(f + ip + 16, p->dst, 4);
		uint16_t c = ip_csum(f + ip, hl);
		f[ip + 10] = c >> 8; f[ip + 11] = c;
		n = ip + tot;
	}
	while (n < 60) f[n++] = 0;                  /* Ethernet minimum frame size */
	return n;
}

static int parse_ip(const char *s, uint8_t ip[4])
{
	unsigned a, b, c, d;
	if (sscanf(s, "%u.%u.%u.%u", &a, &b, &c, &d) != 4) return -1;
	ip[0] = a; ip[1] = b; ip[2] = c; ip[3] = d;
	return 0;
}

static int set_field(pkt_t *p, const char *kv)
{
	char key[32];
	const char *eq = strchr(kv, '=');
	if (!eq || eq - kv >= (int)sizeof key) return -1;
	memcpy(key, kv, eq - kv); key[eq - kv] = 0;
	const char *v = eq + 1;
	if (!strcmp(key, "flags")) {                /* letters F S R P A U, or 'none' */
		p->flags = 0;
		for (; *v; v++) {
			const char *pos = strchr("FSRPAU", toupper((unsigned char)*v));
			if (pos) p->flags |= 1u << (pos - "FSRPAU");
		}
		return 0;
	}
	if (!strcmp(key, "src")) return parse_ip(v, p->src);
	if (!strcmp(key, "dst")) return parse_ip(v, p->dst);
	int x = atoi(v);
	if (!strcmp(key, "ttl")) p->ttl = x;
	else if (!strcmp(key, "sport")) p->sport = x;
	else if (!strcmp(key, "dport")) p->dport = x;
	else if (!strcmp(key, "win")) p->win = x;
	else if (!strcmp(key, "opts")) p->opts = x;
	else if (!strcmp(key, "payload")) p->payload = x;
	else if (!strcmp(key, "df")) p->df = x;
	else if (!strcmp(key, "mf")) p->mf = x;
	else if (!strcmp(key, "foff")) p->foff = x;
	else if (!strcmp(key, "ihl")) p->ihl = x;
	else if (!strcmp(key, "count")) p->count = x;
	else if (!strcmp(key, "inc")) p->inc = x;
	else if (!strcmp(key, "icmp")) p->icmp = x;
	else if (!strcmp(key, "l4cut")) p->l4cut = x;
	else if (!strcmp(key, "proto")) p->proto = !strcmp(v, "tcp") ? 6 : !strcmp(v, "udp") ? 17 : !strcmp(v, "icmp") ? 1 : x;
	else return -1;
	return 0;
}

static void list_presets(void)
{
	printf("normal traffic:\n");
	for (unsigned i = 0; i < N_PRESETS; i++) if (!presets[i].malicious) printf("  %-10s %s\n", presets[i].name, presets[i].what);
	printf("attacks:\n");
	for (unsigned i = 0; i < N_PRESETS; i++) if (presets[i].malicious) printf("  %-10s %s\n", presets[i].name, presets[i].what);
	printf("special:\n  all        every preset once, in the order above\n");
	printf("fields: ttl= sport= dport= win= opts=<bytes> payload=<bytes> flags=<FSRPAU> src=a.b.c.d dst=a.b.c.d\n"
	       "        df= mf= foff= ihl= icmp=<type> proto=tcp|udp|icmp l4cut=<bytes> count=<n> inc=1 (dport +1 per packet)\n"
	       "e.g.:   snn_test craft syn ttl=200 opts=0      a normal SYN made to look like a flood tool's\n");
}

static int craft(int argc, char **argv)
{
	uint8_t f[1600];
	if (argc < 1 || !strcmp(argv[0], "list")) { list_presets(); return 0; }
	int all = !strcmp(argv[0], "all");
	for (unsigned i = 0; i < N_PRESETS; i++) {
		if (!all && strcmp(argv[0], presets[i].name)) continue;
		pkt_t p = presets[i];
		if (all) p.count = 1;
		for (int a = 1; a < argc; a++) {
			if (!strcmp(argv[a], "hex") || !strcmp(argv[a], "noflush")) continue;
			if (set_field(&p, argv[a])) { fprintf(stderr, "bad field '%s' (see: snn_test craft list)\n", argv[a]); return 2; }
		}
		if (!all) printf("preset '%s': %s\n", p.name, p.what);
		for (int k = 0; k < p.count; k++) {
			unsigned n = build(&p, k, f);
			judge(f, n, n, all ? p.name : NULL);
		}
		if (!all) break;
	}
	if (!n_frames) { fprintf(stderr, "unknown preset '%s' (see: snn_test craft list)\n", argv[0]); return 2; }
	summary();
	return 0;
}

/* ---------------------------------------------------------------- raw hex frame */
static int frame_hex(int argc, char **argv)
{
	static uint8_t f[2048];
	unsigned n = 0;
	int hi = -1;
	char buf[8192];
	for (int a = 0; a < argc; a++) {
		const char *s = argv[a];
		if (!strcmp(s, "hex") || !strcmp(s, "noflush")) continue;
		size_t got = 0;
		if (!strcmp(s, "-")) { got = fread(buf, 1, sizeof buf - 1, stdin); buf[got] = 0; s = buf; }
		for (; *s; s++) {
			if (!isxdigit((unsigned char)*s)) continue;
			int v = isdigit((unsigned char)*s) ? *s - '0' : (tolower((unsigned char)*s) - 'a' + 10);
			if (hi < 0) hi = v; else { if (n < sizeof f) f[n++] = (uint8_t)(hi << 4 | v); hi = -1; }
		}
	}
	if (n < 14) { fprintf(stderr, "need at least 14 hex bytes (an Ethernet header)\n"); return 2; }
	judge(f, n, n, NULL);
	return 0;
}

/* ---------------------------------------------------------------- pcap file */
static uint32_t rd32(const uint8_t *p, int sw) { uint32_t v; memcpy(&v, p, 4); return sw ? __builtin_bswap32(v) : v; }

static int pcap_file(int argc, char **argv)
{
	if (argc < 1) { fprintf(stderr, "usage: snn_test pcap <file.pcap> [max]\n"); return 2; }
	FILE *fp = fopen(argv[0], "rb");
	if (!fp) { perror(argv[0]); return 1; }
	unsigned max = argc > 1 && isdigit((unsigned char)argv[1][0]) ? (unsigned)atoi(argv[1]) : 0;
	uint8_t gh[24], rh[16];
	static uint8_t pkt[65536], eth[65536];
	if (fread(gh, 1, 24, fp) != 24) { fprintf(stderr, "not a pcap file\n"); return 1; }
	uint32_t magic; memcpy(&magic, gh, 4);
	int sw;
	if (magic == 0xa1b2c3d4 || magic == 0xa1b23c4d) sw = 0;
	else if (magic == 0xd4c3b2a1 || magic == 0x4d3cb2a1) sw = 1;
	else if (magic == 0x0a0d0d0a) { fprintf(stderr, "pcapng is not supported: capture with 'tcpdump -w' (classic pcap) or convert with 'editcap -F pcap in.pcapng out.pcap'\n"); return 1; }
	else { fprintf(stderr, "not a pcap file (magic 0x%08x)\n", magic); return 1; }
	uint32_t link = rd32(gh + 20, sw);
	if (link != 1 && link != 113 && link != 276) {
		fprintf(stderr, "link type %u not supported (need Ethernet=1 or Linux cooked=113/276)\n", link);
		return 1;
	}
	while (fread(rh, 1, 16, fp) == 16) {
		uint32_t cap = rd32(rh + 8, sw), orig = rd32(rh + 12, sw);
		if (cap > sizeof pkt || fread(pkt, 1, cap, fp) != cap) break;
		const uint8_t *f = pkt;
		unsigned avail = cap, len = orig;
		if (link == 113 || link == 276) {            /* Linux cooked capture: rebuild an Ethernet header */
			unsigned hl = link == 113 ? 16 : 20, pt = link == 113 ? 14 : 0;
			if (cap < hl) continue;
			memset(eth, 0, 12);
			eth[12] = pkt[pt]; eth[13] = pkt[pt + 1];
			memcpy(eth + 14, pkt + hl, cap - hl);
			f = eth; avail = cap - hl + 14; len = orig - hl + 14;
		}
		judge(f, avail, len, NULL);
		if (max && n_frames >= max) break;
	}
	fclose(fp);
	summary();
	return 0;
}

/* ---------------------------------------------------------------- live interface */
static volatile sig_atomic_t stop_flag;
static void on_sigint(int s) { (void)s; stop_flag = 1; }

static int sniff(int argc, char **argv)
{
	const char *ifn = argc > 0 && !isdigit((unsigned char)argv[0][0]) ? argv[0] : "wlan0";
	unsigned count = 0;
	for (int a = 0; a < argc; a++) if (isdigit((unsigned char)argv[a][0])) count = (unsigned)atoi(argv[a]);
	int s = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL));
	if (s < 0) { perror("socket(AF_PACKET) (run as root)"); return 1; }
	struct sockaddr_ll sa;
	memset(&sa, 0, sizeof sa);
	sa.sll_family = AF_PACKET;
	sa.sll_protocol = htons(ETH_P_ALL);
	sa.sll_ifindex = (int)if_nametoindex(ifn);
	if (!sa.sll_ifindex || bind(s, (struct sockaddr *)&sa, sizeof sa)) { perror(ifn); return 1; }
	struct sigaction act;
	memset(&act, 0, sizeof act);
	act.sa_handler = on_sigint;
	sigaction(SIGINT, &act, NULL);
	printf("classifying frames received on %s%s (Ctrl-C to stop); this only watches, nothing is dropped\n",
	       ifn, count ? "" : " until Ctrl-C");
	static uint8_t f[65536];
	while (!stop_flag && (!count || n_frames < count)) {
		struct sockaddr_ll from;
		socklen_t fl = sizeof from;
		ssize_t r = recvfrom(s, f, sizeof f, MSG_TRUNC, (struct sockaddr *)&from, &fl);
		if (r < 0) { if (errno == EINTR) continue; perror("recvfrom"); break; }
		if (from.sll_pkttype == PACKET_OUTGOING) continue;        /* only what the board receives */
		unsigned len = (unsigned)r, avail = len > sizeof f ? sizeof f : len;
		judge(f, avail, len, NULL);
	}
	close(s);
	summary();
	return 0;
}

/* ---------------------------------------------------------------- entry */
int custom_main(int argc, char **argv)
{
	const char *mode = argv[0];
	int flush = 1;
	for (int a = 0; a < argc; a++) {
		if (!strcmp(argv[a], "hex")) opt_hex = 1;
		if (!strcmp(argv[a], "noflush")) flush = 0;
	}
	if (!strcmp(mode, "craft") && (argc < 2 || !strcmp(argv[1], "list"))) { list_presets(); return 0; }
	load_weights();
	drain();
	if (flush) flush_rate_window();
	if (!strcmp(mode, "craft")) return craft(argc - 1, argv + 1);
	if (!strcmp(mode, "frame")) return frame_hex(argc - 1, argv + 1);
	if (!strcmp(mode, "pcap"))  return pcap_file(argc - 1, argv + 1);
	if (!strcmp(mode, "sniff")) return sniff(argc - 1, argv + 1);
	return -1;
}
