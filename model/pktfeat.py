"""
Bit-exact golden model of the hardware packet parser + spike encoder.

The RTL (rtl/pkt_parser.v + rtl/spike_encoder.v) MUST produce exactly the
same 64-bit spike vector for every frame. Any change here has to be mirrored
in RTL (and vice-versa).

Frame = Ethernet frame as delivered by the MAC on its AXI-Stream RX port
(dst MAC first, FCS already stripped). Bytes beyond the frame end read as 0
(the RTL clears its field registers at start of every frame).
"""

N_IN = 64

# Rate monitor (sliding window over the last RATE_WIN frames, incl. current)
RATE_WIN = 32
RATE_T1 = 8
RATE_T2 = 16

SENSITIVE_PORTS = (22, 23, 445, 3389)

FEATURE_NAMES = [
    "bias",
    "l3_ipv4", "l3_arp", "l3_ipv6", "l3_other",
    "p_tcp", "p_udp", "p_icmp", "p_other",
    "ihl_eq5", "ihl_gt5", "ihl_lt5",
    "ip_df", "ip_mf", "ip_fragoff",
    "ttl_le8", "ttl_9_64", "ttl_65_128", "ttl_gt128",
    "len_le40", "len_41_100", "len_101_576", "len_577_1500", "len_gt1500",
    "land", "src_bogon", "dst_bcast",
    "tcp_fin", "tcp_syn", "tcp_rst", "tcp_psh", "tcp_ack", "tcp_urg",
    "tcp_null",
    "dport_0", "dport_wk", "dport_reg", "dport_eph",
    "sport_0", "sport_wk", "sport_reg", "sport_eph",
    "doff_eq5", "doff_gt5", "doff_lt5",
    "win_0", "win_small", "win_large",
    "icmp_echorep", "icmp_echoreq", "icmp_unreach", "icmp_other",
    "pl_le8", "pl_9_64", "pl_65_512", "pl_gt512",
    "len_incons",
    "synrate_t1", "synrate_t2", "icmprate_t1", "icmprate_t2",
    "truncated", "sens_port", "dns_port",
]
assert len(FEATURE_NAMES) == N_IN


def _b(f, i):
    return f[i] if i < len(f) else 0


def _w(f, i):
    return (_b(f, i) << 8) | _b(f, i + 1)


def parse(frame):
    """Header field extraction (mirrors rtl/pkt_parser.v)."""
    flen = len(frame)
    et0 = _w(frame, 12)
    vlan = et0 == 0x8100
    l3 = 18 if vlan else 14
    et = _w(frame, 16) if vlan else et0
    ipv4 = et == 0x0800
    p = dict(flen=flen, l3=l3, et=et, ipv4=ipv4)
    if ipv4:
        ihl = _b(frame, l3) & 0xF
        p["ihl"] = ihl
        p["tot_len"] = _w(frame, l3 + 2)
        ff = _w(frame, l3 + 6)
        p["df"] = (ff >> 14) & 1
        p["mf"] = (ff >> 13) & 1
        p["foff"] = ff & 0x1FFF
        p["ttl"] = _b(frame, l3 + 8)
        p["proto"] = _b(frame, l3 + 9)
        p["src"] = [_b(frame, l3 + 12 + k) for k in range(4)]
        p["dst"] = [_b(frame, l3 + 16 + k) for k in range(4)]
        l4 = l3 + 4 * ihl
        p["l4"] = l4
        has_l4 = ihl >= 5 and p["foff"] == 0
        p["has_l4"] = has_l4
        # L4 fields are only captured when has_l4 (RTL gates capture enables)
        g = (lambda i: _b(frame, l4 + i)) if has_l4 else (lambda i: 0)
        gw = (lambda i: (g(i) << 8) | g(i + 1))
        p["sport"] = gw(0)
        p["dport"] = gw(2)
        p["l4_b4"] = gw(4)            # UDP length
        p["icmp_type"] = g(0)
        p["doff"] = g(12) >> 4
        p["tflags"] = g(13)
        p["win"] = gw(14)
    return p


class RateMonitor:
    """Sliding-window counters of pure-SYN and ICMP-echo-request frames."""

    def __init__(self):
        self.syn = [0] * RATE_WIN
        self.icmp = [0] * RATE_WIN

    def update(self, is_syn, is_echo):
        self.syn = self.syn[1:] + [int(is_syn)]
        self.icmp = self.icmp[1:] + [int(is_echo)]
        return sum(self.syn), sum(self.icmp)


def encode(p, syn_cnt, icmp_cnt):
    """Field dict + window counts -> list of 64 binary spikes."""
    s = [0] * N_IN
    s[0] = 1
    et = p["et"]
    s[1] = int(p["ipv4"])
    s[2] = int(et == 0x0806)
    s[3] = int(et == 0x86DD)
    s[4] = int(not (s[1] or s[2] or s[3]))
    flen = p["flen"]
    l3 = p["l3"]
    trunc = flen < l3 + 20 if p["ipv4"] else flen < l3
    if p["ipv4"]:
        pr = p["proto"]
        tcp, udp, icmp = pr == 6, pr == 17, pr == 1
        s[5], s[6], s[7] = int(tcp), int(udp), int(icmp)
        s[8] = int(not (tcp or udp or icmp))
        ihl = p["ihl"]
        s[9], s[10], s[11] = int(ihl == 5), int(ihl > 5), int(ihl < 5)
        s[12], s[13], s[14] = p["df"], p["mf"], int(p["foff"] != 0)
        t = p["ttl"]
        s[15], s[16], s[17], s[18] = int(t <= 8), int(9 <= t <= 64), int(65 <= t <= 128), int(t > 128)
        L = p["tot_len"]
        s[19] = int(L <= 40)
        s[20] = int(41 <= L <= 100)
        s[21] = int(101 <= L <= 576)
        s[22] = int(577 <= L <= 1500)
        s[23] = int(L > 1500)
        s[24] = int(p["src"] == p["dst"])
        s0 = p["src"][0]
        s[25] = int(s0 == 0 or s0 == 127 or s0 >= 224)
        d = p["dst"]
        s[26] = int(d[3] == 255)
        hl4 = p["has_l4"]
        if tcp and hl4:
            f = p["tflags"]
            for k in range(6):            # FIN SYN RST PSH ACK URG
                s[27 + k] = (f >> k) & 1
            s[33] = int((f & 0x3F) == 0)
            do = p["doff"]
            s[42], s[43], s[44] = int(do == 5), int(do > 5), int(do < 5)
            w = p["win"]
            s[45], s[46], s[47] = int(w == 0), int(1 <= w <= 1023), int(w >= 1024)
        if (tcp or udp) and hl4:
            for base, port in ((34, p["dport"]), (38, p["sport"])):
                s[base + 0] = int(port == 0)
                s[base + 1] = int(1 <= port <= 1023)
                s[base + 2] = int(1024 <= port <= 49151)
                s[base + 3] = int(port >= 49152)
            s[62] = int(p["dport"] in SENSITIVE_PORTS)
            s[63] = int(p["dport"] == 53 or p["sport"] == 53)
        if icmp and hl4:
            ty = p["icmp_type"]
            s[48], s[49], s[50] = int(ty == 0), int(ty == 8), int(ty == 3)
            s[51] = int(ty not in (0, 3, 8))
        pl = L - 4 * ihl          # may be negative for malformed headers
        s[52] = int(pl <= 8)
        s[53] = int(9 <= pl <= 64)
        s[54] = int(65 <= pl <= 512)
        s[55] = int(pl > 512)
        s[56] = int(L > flen - l3 or L < 4 * ihl)
        if hl4:
            need = 20 if tcp else 8 if udp else 4 if icmp else 0
            trunc = trunc or flen < p["l4"] + need
    s[57] = int(syn_cnt >= RATE_T1)
    s[58] = int(syn_cnt >= RATE_T2)
    s[59] = int(icmp_cnt >= RATE_T1)
    s[60] = int(icmp_cnt >= RATE_T2)
    s[61] = int(trunc)
    return s


def rate_events(p):
    if not p["ipv4"] or not p["has_l4"]:
        return False, False
    is_syn = p["proto"] == 6 and (p["tflags"] & 0x12) == 0x02
    is_echo = p["proto"] == 1 and p["icmp_type"] == 8
    return is_syn, is_echo


def encode_stream(frames):
    """Encode a list of frames (bytes) in arrival order -> list of spike lists."""
    rm = RateMonitor()
    out = []
    for fr in frames:
        p = parse(fr)
        sc, ic = rm.update(*rate_events(p))
        out.append(encode(p, sc, ic))
    return out


def spikes_to_int(s):
    v = 0
    for i, b in enumerate(s):
        v |= (b & 1) << i
    return v
