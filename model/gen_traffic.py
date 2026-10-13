"""
Synthetic labelled Ethernet traffic generator (no external deps).

Produces an ordered packet stream (order matters: the encoder has a sliding
rate window) mixing benign background traffic with attack episodes.
Per-packet label: 0 = benign, 1 = malicious, plus an attack-type string.

This is a stand-in until real captures (CIC-IDS2017 / UNSW-NB15 / CIC-DDoS2019
pcaps) are plugged in via model/pcap_io.py.
"""
import random
import struct

ETH_IPV4, ETH_ARP, ETH_IPV6, ETH_VLAN = 0x0800, 0x0806, 0x86DD, 0x8100


def csum(b):
    if len(b) % 2:
        b += b"\0"
    s = sum(struct.unpack("!%dH" % (len(b) // 2), b))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


BURSTY = ("syn_flood", "icmp_flood", "dns_amp", "scan_syn", "smurf")


class Gen:
    def __init__(self, seed=1):
        self.r = random.Random(seed)
        self.hosts = [self.priv_ip() for _ in range(40)]
        self.servers = [self.pub_ip() for _ in range(60)]
        self.mac = {}

    # ---------------------------------------------------------------- helpers
    def priv_ip(self):
        r = self.r
        return [192, 168, r.randint(0, 3), r.randint(2, 250)]

    def pub_ip(self):
        r = self.r
        while True:
            a = r.randint(1, 223)
            if a not in (10, 127, 172, 192):
                return [a, r.randint(0, 255), r.randint(0, 255), r.randint(1, 254)]

    def macaddr(self, ip):
        k = tuple(ip)
        if k not in self.mac:
            self.mac[k] = bytes([0x02] + [self.r.randint(0, 255) for _ in range(5)])
        return self.mac[k]

    def eth(self, src_ip, dst_ip, et, payload, vlan=None):
        if vlan is None:
            vlan = self.r.random() < 0.08
        hdr = self.macaddr(dst_ip) + self.macaddr(src_ip)
        if vlan:
            hdr += struct.pack("!HH", ETH_VLAN, self.r.randint(1, 4094))
        fr = hdr + struct.pack("!H", et) + payload
        if len(fr) < 60:
            fr += b"\0" * (60 - len(fr))
        return fr

    def ipv4(self, src, dst, proto, l4, ttl=None, df=None, mf=0, foff=0,
             ihl=5, tot_len=None, opts=b""):
        r = self.r
        if ttl is None:
            ttl = r.choice([64, 128, 255]) - r.randint(0, 20)
        if df is None:
            df = int(r.random() < 0.7)
        hdr_len = max(ihl, 0) * 4
        opts = opts[:max(0, hdr_len - 20)]
        if tot_len is None:
            tot_len = 20 + len(opts) + len(l4)
        ff = (df << 14) | (mf << 13) | (foff & 0x1FFF)
        h = struct.pack("!BBHHHBBH4B4B", (4 << 4) | (ihl & 0xF), 0, tot_len & 0xFFFF,
                        r.randint(0, 65535), ff, ttl & 0xFF, proto, 0, *src, *dst)
        h = h + opts
        h = h[:10] + struct.pack("!H", csum(h)) + h[12:]
        return h + l4

    def tcp(self, sp, dp, flags, payload=b"", win=None, doff=5, seq=None):
        r = self.r
        if win is None:
            win = r.choice([64240, 65535, 29200, 8192, 502, 1026])
        opts = b"\x02\x04\x05\xb4" + b"\x01" * 36
        opts = opts[:max(0, (doff - 5) * 4)]
        h = struct.pack("!HHIIBBHHH", sp, dp, seq if seq is not None else r.getrandbits(32),
                        r.getrandbits(32), (doff & 0xF) << 4, flags, win, 0, 0)
        return h + opts + payload

    def udp(self, sp, dp, payload, ulen=None):
        return struct.pack("!HHHH", sp, dp, ulen if ulen is not None else 8 + len(payload), 0) + payload

    def icmp(self, ty, code=0, payload=b""):
        return struct.pack("!BBHI", ty, code, 0, self.r.getrandbits(32)) + payload

    def rb(self, n):
        return bytes(self.r.getrandbits(8) for _ in range(n))

    def eport(self):
        return self.r.randint(49152, 65535) if self.r.random() < 0.7 else self.r.randint(1024, 49151)

    def frame_ip(self, src, dst, proto, l4, **kw):
        vlan = kw.pop("vlan", None)
        return self.eth(src, dst, ETH_IPV4, self.ipv4(src, dst, proto, l4, **kw), vlan=vlan)

    # ---------------------------------------------------------------- benign
    def tcp_session(self):
        r = self.r
        c, s = r.choice(self.hosts), r.choice(self.servers)
        cp = self.eport()
        sp = r.choice([80, 443, 443, 443, 22, 8080, 25, 993, 3306, 5432])
        ttl_c, ttl_s = 64, r.choice([52, 56, 115, 118, 240])
        F = []
        F.append(self.frame_ip(c, s, 6, self.tcp(cp, sp, 0x02, doff=r.choice([6, 8, 10]), win=64240), ttl=ttl_c, df=1))
        F.append(self.frame_ip(s, c, 6, self.tcp(sp, cp, 0x12, doff=r.choice([6, 8, 10])), ttl=ttl_s, df=1))
        F.append(self.frame_ip(c, s, 6, self.tcp(cp, sp, 0x10, doff=r.choice([5, 8])), ttl=ttl_c, df=1))
        for _ in range(r.randint(1, 10)):
            if r.random() < 0.5:
                F.append(self.frame_ip(c, s, 6, self.tcp(cp, sp, 0x18, self.rb(r.randint(20, 600)), doff=r.choice([5, 8])), ttl=ttl_c, df=1))
            else:
                F.append(self.frame_ip(s, c, 6, self.tcp(sp, cp, r.choice([0x18, 0x10]), self.rb(r.randint(100, 1440)), doff=r.choice([5, 8])), ttl=ttl_s, df=1))
            F.append(self.frame_ip(c, s, 6, self.tcp(cp, sp, 0x10, doff=r.choice([5, 8])), ttl=ttl_c, df=1))
        end = r.random()
        if end < 0.8:
            F.append(self.frame_ip(c, s, 6, self.tcp(cp, sp, 0x11), ttl=ttl_c, df=1))
            F.append(self.frame_ip(s, c, 6, self.tcp(sp, cp, 0x11), ttl=ttl_s, df=1))
            F.append(self.frame_ip(c, s, 6, self.tcp(cp, sp, 0x10), ttl=ttl_c, df=1))
        elif end < 0.95:
            F.append(self.frame_ip(c, s, 6, self.tcp(cp, sp, 0x14, win=0), ttl=ttl_c, df=1))
        return F

    def dns(self):
        r = self.r
        c, s = r.choice(self.hosts), r.choice([[8, 8, 8, 8], [1, 1, 1, 1], [192, 168, 0, 1]])
        cp = self.eport()
        q = self.frame_ip(c, s, 17, self.udp(cp, 53, self.rb(r.randint(20, 60))), ttl=64)
        a = self.frame_ip(s, c, 17, self.udp(53, cp, self.rb(r.randint(40, 700))), ttl=r.choice([56, 60, 64]))
        return [q, a]

    def udp_misc(self):
        r = self.r
        c, s = r.choice(self.hosts), r.choice(self.servers)
        kind = r.random()
        if kind < 0.5:   # QUIC
            cp = self.eport()
            return [self.frame_ip(c, s, 17, self.udp(cp, 443, self.rb(r.randint(1200, 1350))), ttl=64),
                    self.frame_ip(s, c, 17, self.udp(443, cp, self.rb(r.randint(30, 1350))), ttl=r.choice([52, 115]))]
        if kind < 0.75:  # NTP
            return [self.frame_ip(c, s, 17, self.udp(123, 123, self.rb(48)), ttl=64)]
        # mDNS / SSDP style multicast
        return [self.frame_ip(c, [224, 0, 0, 251], 17, self.udp(5353, 5353, self.rb(r.randint(30, 300))), ttl=255)]

    def ping(self):
        r = self.r
        c, s = r.choice(self.hosts), r.choice(self.servers)
        pl = self.rb(56)
        out = []
        for _ in range(r.randint(1, 4)):
            out.append(self.frame_ip(c, s, 1, self.icmp(8, payload=pl), ttl=64))
            if r.random() < 0.9:
                out.append(self.frame_ip(s, c, 1, self.icmp(0, payload=pl), ttl=r.choice([52, 115])))
        return out

    def icmp_unreach(self):
        r = self.r
        c, s = r.choice(self.hosts), r.choice(self.servers)
        inner = self.ipv4(c, s, 17, self.udp(self.eport(), 33434, b""))[:28]
        return [self.frame_ip(s, c, 1, self.icmp(3, 3, inner), ttl=r.choice([52, 250]))]

    def arp(self):
        r = self.r
        a, b = r.choice(self.hosts), r.choice(self.hosts)
        body = struct.pack("!HHBBH", 1, 0x0800, 6, 4, r.choice([1, 2])) + self.macaddr(a) + bytes(a) + b"\0" * 6 + bytes(b)
        return [self.eth(a, b, ETH_ARP, body)]

    def ipv6(self):
        r = self.r
        a = r.choice(self.hosts)
        return [self.eth(a, r.choice(self.servers), ETH_IPV6, self.rb(r.randint(40, 1400)))]

    def legit_frag(self):
        r = self.r
        c, s = r.choice(self.hosts), r.choice(self.servers)
        data = self.rb(1472)
        f1 = self.frame_ip(c, s, 17, self.udp(self.eport(), r.choice([4500, 443, 5004]), data, ulen=8 + 1472 + 400)[:1480], df=0, mf=1, foff=0)
        f2 = self.frame_ip(c, s, 17, self.rb(400), df=0, mf=0, foff=185)
        return [f1, f2]

    def benign(self):
        r = self.r
        k = r.random()
        if k < 0.42:
            return self.tcp_session()
        if k < 0.60:
            return self.dns()
        if k < 0.72:
            return self.udp_misc()
        if k < 0.80:
            return self.ping()
        if k < 0.84:
            return self.icmp_unreach()
        if k < 0.91:
            return self.arp()
        if k < 0.97:
            return self.ipv6()
        return self.legit_frag()

    # ---------------------------------------------------------------- attacks
    # Each returns (list_of_frames, name); every frame is malicious.
    def syn_flood(self):
        r = self.r
        v, dp = r.choice(self.servers), r.choice([80, 443])
        n = r.randint(30, 160)
        F = []
        for _ in range(n):
            src = self.pub_ip() if r.random() < 0.8 else [r.choice([0, 127, 240]), r.randint(0, 255), r.randint(0, 255), r.randint(1, 254)]
            F.append(self.frame_ip(src, v, 6, self.tcp(r.randint(1024, 65535), dp, 0x02, win=r.choice([512, 1024, 5840, 64240]),
                                                         doff=r.choice([5, 5, 6])), ttl=r.randint(30, 255), df=r.randint(0, 1)))
        return F, "syn_flood"

    def port_scan(self):
        r = self.r
        a, v = self.pub_ip(), r.choice(self.hosts)
        kind = r.choice(["syn", "null", "xmas", "fin", "synfin", "ack", "maimon"])
        flags = dict(syn=0x02, null=0x00, xmas=0x29, fin=0x01, synfin=0x03, ack=0x10, maimon=0x11)[kind]
        sp = r.randint(30000, 65000)
        F = []
        base = r.randint(1, 60000)
        for i in range(r.randint(10, 80)):
            dp = (base + i) % 65536 if r.random() < 0.6 else r.randint(1, 1024)
            F.append(self.frame_ip(a, v, 6, self.tcp(sp, dp, flags, win=1024, doff=r.choice([5, 6])), ttl=r.randint(37, 59), df=0))
        return F, "scan_" + kind

    def udp_scan(self):
        r = self.r
        a, v = self.pub_ip(), r.choice(self.hosts)
        sp = r.randint(30000, 65000)
        return [self.frame_ip(a, v, 17, self.udp(sp, r.randint(1, 1024), b""), ttl=r.randint(37, 59), df=0)
                for _ in range(r.randint(10, 50))], "udp_scan"

    def land(self):
        v = self.r.choice(self.servers)
        p = self.r.choice([80, 139, 445])
        return [self.frame_ip(v, v, 6, self.tcp(p, p, 0x02)) for _ in range(self.r.randint(1, 5))], "land"

    def ping_of_death(self):
        r = self.r
        a, v = self.pub_ip(), r.choice(self.hosts)
        F = []
        for i in range(r.randint(3, 12)):
            F.append(self.frame_ip(a, v, 1, self.rb(1480), df=0, mf=1, foff=8000 + 185 * i))
        F.append(self.frame_ip(a, v, 1, self.rb(r.randint(400, 1480)), df=0, mf=0, foff=8191 - 200))
        return F, "ping_of_death"

    def icmp_flood(self):
        r = self.r
        v = r.choice(self.hosts)
        return [self.frame_ip(self.pub_ip(), v, 1, self.icmp(8, payload=self.rb(r.choice([0, 56, 1000, 1472]))), ttl=r.randint(30, 255))
                for _ in range(r.randint(30, 150))], "icmp_flood"

    def smurf(self):
        r = self.r
        v = r.choice(self.servers)
        net = r.choice(self.hosts)
        return [self.frame_ip(v, [net[0], net[1], net[2], 255], 1, self.icmp(8, payload=self.rb(56)), ttl=r.randint(30, 255))
                for _ in range(r.randint(3, 20))], "smurf"

    def tiny_frag(self):
        r = self.r
        a, v = self.pub_ip(), r.choice(self.hosts)
        F = []
        for _ in range(r.randint(2, 10)):
            proto = r.choice([6, 17])
            F.append(self.frame_ip(a, v, proto, self.rb(8), df=0, mf=1, foff=r.choice([0, 1, 2])))
        return F, "tiny_frag"

    def teardrop(self):
        r = self.r
        a, v = self.pub_ip(), r.choice(self.hosts)
        return [self.frame_ip(a, v, 17, self.udp(r.randint(1, 65535), r.randint(1, 65535), self.rb(28)), df=0, mf=1, foff=0),
                self.frame_ip(a, v, 17, self.rb(r.randint(4, 20)), df=0, mf=0, foff=r.randint(1, 3))], "teardrop"

    def malformed(self):
        r = self.r
        a, v = self.pub_ip(), r.choice(self.hosts)
        k = r.choice(["ihl", "doff", "len", "len2"])
        if k == "ihl":
            f = self.frame_ip(a, v, 6, self.tcp(r.randint(1, 65535), 80, 0x02), ihl=r.randint(0, 4))
        elif k == "doff":
            f = self.frame_ip(a, v, 6, self.tcp(r.randint(1, 65535), r.choice([80, 445]), 0x18, self.rb(20), doff=r.randint(0, 4)))
        elif k == "len":
            f = self.frame_ip(a, v, 17, self.udp(r.randint(1, 65535), 53, self.rb(20)), tot_len=r.randint(200, 65535))
        else:
            f = self.frame_ip(a, v, 6, self.tcp(r.randint(1, 65535), 80, 0x18, self.rb(20)), tot_len=r.randint(0, 19))
        return [f], "malformed_" + k

    def bogon_spoof(self):
        r = self.r
        v = r.choice(self.hosts)
        src = [r.choice([0, 127, 224, 240, 255]), r.randint(0, 255), r.randint(0, 255), r.randint(1, 254)]
        return [self.frame_ip(src, v, r.choice([6, 17]),
                              self.tcp(r.randint(1, 65535), r.choice([80, 22, 445]), 0x02) if r.random() < 0.5 else
                              self.udp(r.randint(1, 65535), r.choice([53, 161, 123]), self.rb(40)))
                for _ in range(r.randint(1, 6))], "bogon_spoof"

    def port0(self):
        r = self.r
        a, v = self.pub_ip(), r.choice(self.hosts)
        return [self.frame_ip(a, v, r.choice([6, 17]),
                              self.tcp(r.randint(1024, 65535), 0, 0x02) if r.random() < 0.5 else self.udp(r.randint(1024, 65535), 0, self.rb(16)))
                for _ in range(r.randint(1, 5))], "port0"

    def dns_amp(self):
        r = self.r
        v = r.choice(self.hosts)
        return [self.frame_ip(self.pub_ip(), v, 17, self.udp(53, r.randint(1024, 65535), self.rb(r.randint(1200, 1450))),
                              ttl=r.randint(40, 250), df=0) for _ in range(r.randint(20, 80))], "dns_amp"

    def lowttl_evasion(self):
        r = self.r
        a, v = self.pub_ip(), r.choice(self.hosts)
        return [self.frame_ip(a, v, 6, self.tcp(r.randint(1024, 65535), 80, 0x18, self.rb(r.randint(10, 100))), ttl=r.randint(0, 3))
                for _ in range(r.randint(1, 6))], "ttl_evasion"

    def attack(self):
        r = self.r
        fns = [(self.syn_flood, 3), (self.port_scan, 4), (self.udp_scan, 1), (self.land, 1), (self.ping_of_death, 1),
               (self.icmp_flood, 2), (self.smurf, 1), (self.tiny_frag, 1), (self.teardrop, 1), (self.malformed, 2),
               (self.bogon_spoof, 1), (self.port0, 1), (self.dns_amp, 1), (self.lowttl_evasion, 1)]
        tot = sum(w for _, w in fns)
        x = r.uniform(0, tot)
        for f, w in fns:
            x -= w
            if x <= 0:
                return f()
        return fns[0][0]()

    # ---------------------------------------------------------------- stream
    def stream(self, n_packets, quiet=(40, 300)):
        """Ordered stream: benign background flows, with one attack episode at a
        time injected between quiet periods. Floods dominate the link while
        active; other attacks are sparse among background traffic."""
        r = self.r
        out = []
        flows = []
        attack, p_att, quiet_left = None, 0.0, r.randint(*quiet)

        def bg():
            while len(flows) < 6:
                flows.append(iter([(f, 0, "benign") for f in self.benign()]))
            it = r.choice(flows)
            for x in it:
                return x
            flows.remove(it)
            return bg()

        while len(out) < n_packets:
            if attack is None:
                if quiet_left > 0:
                    quiet_left -= 1
                else:
                    F, name = self.attack()
                    attack = iter([(f, 1, name) for f in F])
                    p_att = r.uniform(0.6, 0.9) if name in BURSTY else r.uniform(0.15, 0.4)
            if attack is not None and r.random() < p_att:
                x = next(attack, None)
                if x is None:
                    attack, quiet_left = None, r.randint(*quiet)
                    continue
                out.append(x)
            else:
                out.append(bg())
        return out[:n_packets]


if __name__ == "__main__":
    g = Gen(1)
    s = g.stream(5000)
    from collections import Counter
    print(Counter(k for _, _, k in s))
    print("malicious frac", sum(l for _, l, _ in s) / len(s))
