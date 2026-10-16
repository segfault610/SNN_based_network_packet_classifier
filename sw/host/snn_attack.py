#!/usr/bin/env python3
"""
snn_attack.py - send attack-shaped packets from your laptop to your own Chameleon96 board, to test
whether the SNN firewall flags them. It's the sender side of 'snn_test craft' on the board, so the
same presets produce the same verdicts. On the board run './snn_test sniff wlan0' (or load snn_fw.ko)
and watch LED1 and the printed verdicts while this runs.

Only use it against hardware you own, on your own network. It needs root (raw sockets):

  sudo python3 sw/host/snn_attack.py <board-ip> list
  sudo python3 sw/host/snn_attack.py <board-ip> <preset> [field=value ...]
  sudo python3 sw/host/snn_attack.py <board-ip> all           # one of every preset
  sudo python3 sw/host/snn_attack.py <board-ip> attacks       # every attack preset
       python3 sw/host/snn_attack.py <board-ip> <preset> --dry-run   # show the verdict the SNN should
                                                                      # give, WITHOUT sending (no root)

Presets and fields mirror sw/cv96/tools/snn_custom.c; see docs/custom_traffic_cv96.md.
The packets are real IP packets addressed to the board, so normal frames (syn, ping, ...) actually
reach its stack; spoofed-source presets (bogon, land) may be filtered by some access points.
"""
import os
import socket
import struct
import sys
import time

# ---------------------------------------------------------------- presets (name: fields; dst filled from the CLI)
# proto: 6 TCP, 17 UDP, 1 ICMP.  flags: TCP flag bits.  mal: what it is meant to be (printout only).
P = [
    dict(name="syn",       proto=6,  flags=0x02, ttl=64,  sport=51234, dport=443, win=64240, opts=12, pay=0,    df=1, icmp=0, cnt=1,  inc=0, mal=0, what="normal client SYN (TCP options, TTL 64)"),
    dict(name="ack",       proto=6,  flags=0x10, ttl=64,  sport=51234, dport=443, win=64240, opts=12, pay=0,    df=1, icmp=0, cnt=1,  inc=0, mal=0, what="acknowledgement inside a connection"),
    dict(name="data",      proto=6,  flags=0x18, ttl=64,  sport=51234, dport=443, win=64240, opts=12, pay=300,  df=1, icmp=0, cnt=1,  inc=0, mal=0, what="web data (PSH+ACK, 300 B)"),
    dict(name="fin",       proto=6,  flags=0x11, ttl=64,  sport=51234, dport=443, win=64240, opts=0,  pay=0,    df=1, icmp=0, cnt=1,  inc=0, mal=0, what="polite close (FIN+ACK)"),
    dict(name="ping",      proto=1,  flags=0,    ttl=64,  sport=0,     dport=0,   win=0,     opts=0,  pay=56,   df=0, icmp=8, cnt=1,  inc=0, mal=0, what="normal ping, 56 B"),
    dict(name="dns",       proto=17, flags=0,    ttl=64,  sport=53111, dport=53,  win=0,     opts=0,  pay=32,   df=0, icmp=0, cnt=1,  inc=0, mal=0, what="DNS query"),
    dict(name="synflood",  proto=6,  flags=0x02, ttl=200, sport=4000,  dport=80,  win=512,   opts=0,  pay=0,    df=0, icmp=0, cnt=40, inc=0, mal=1, what="SYN flood: bare SYNs, no options, TTL 200 (x40)", src="203.0.113.9"),
    dict(name="synscan",   proto=6,  flags=0x02, ttl=45,  sport=41000, dport=1,   win=1024,  opts=0,  pay=0,    df=0, icmp=0, cnt=25, inc=1, mal=1, what="SYN scan, ports 1-25",                       src="198.51.100.7"),
    dict(name="xmas",      proto=6,  flags=0x29, ttl=45,  sport=41000, dport=1,   win=1024,  opts=0,  pay=0,    df=0, icmp=0, cnt=25, inc=1, mal=1, what="Xmas scan (FIN+PSH+URG), ports 1-25",        src="198.51.100.7"),
    dict(name="null",      proto=6,  flags=0x00, ttl=45,  sport=41000, dport=1,   win=1024,  opts=0,  pay=0,    df=0, icmp=0, cnt=25, inc=1, mal=1, what="NULL scan (no flags), ports 1-25",           src="198.51.100.7"),
    dict(name="finscan",   proto=6,  flags=0x01, ttl=45,  sport=41000, dport=1,   win=1024,  opts=0,  pay=0,    df=0, icmp=0, cnt=25, inc=1, mal=1, what="FIN scan, ports 1-25",                       src="198.51.100.7"),
    dict(name="ackscan",   proto=6,  flags=0x10, ttl=45,  sport=41000, dport=1,   win=1024,  opts=0,  pay=0,    df=0, icmp=0, cnt=25, inc=1, mal=1, what="ACK scan, ports 1-25",                       src="198.51.100.7"),
    dict(name="udpscan",   proto=17, flags=0,    ttl=45,  sport=41000, dport=1,   win=0,     opts=0,  pay=0,    df=0, icmp=0, cnt=25, inc=1, mal=1, what="UDP scan, ports 1-25",                       src="198.51.100.7"),
    dict(name="port0",     proto=6,  flags=0x02, ttl=64,  sport=30000, dport=0,   win=1024,  opts=0,  pay=0,    df=1, icmp=0, cnt=3,  inc=0, mal=1, what="SYN to port 0 (invalid)",                    src="198.51.100.7"),
    dict(name="land",      proto=6,  flags=0x02, ttl=64,  sport=80,    dport=80,  win=1024,  opts=0,  pay=0,    df=1, icmp=0, cnt=3,  inc=0, mal=1, what="land attack: source = destination (src set to the board)", src="DST"),
    dict(name="pingflood", proto=1,  flags=0,    ttl=200, sport=0,     dport=0,   win=0,     opts=0,  pay=1000, df=0, icmp=8, cnt=40, inc=0, mal=1, what="ping flood: 1000 B pings, TTL 200 (x40)",    src="203.0.113.9"),
    dict(name="smurf",     proto=1,  flags=0,    ttl=90,  sport=0,     dport=0,   win=0,     opts=0,  pay=56,   df=0, icmp=8, cnt=5,  inc=0, mal=1, what="ping to a broadcast destination",            dst_override="broadcast"),
    dict(name="bogon",     proto=6,  flags=0x02, ttl=64,  sport=30000, dport=22,  win=1024,  opts=0,  pay=0,    df=1, icmp=0, cnt=3,  inc=0, mal=1, what="SYN from an impossible source (127.x)",     src="127.4.5.6"),
    dict(name="lowttl",    proto=6,  flags=0x18, ttl=1,   sport=30000, dport=80,  win=64240, opts=0,  pay=40,   df=1, icmp=0, cnt=3,  inc=0, mal=1, what="data with TTL 1 (evasion trick)",           src="198.51.100.7"),
]
BY_NAME = {p["name"]: p for p in P}
INT_FIELDS = dict(ttl="ttl", sport="sport", dport="dport", win="win", opts="opts", payload="pay",
                  df="df", icmp="icmp", count="cnt", inc="inc", mf="mf", foff="foff", ihl="ihl")


def ipn(s):
    return struct.unpack("!I", socket.inet_aton(s))[0]


def checksum(data):
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return (~s) & 0xFFFF


def build_l4(p, dport, src_i, dst_i):
    proto = p["proto"]
    if proto == 6:
        ob = min((p.get("opts", 0) // 4) * 4, 40)
        off = (5 + ob // 4) << 4
        opts = (b"\x02\x04\x05\xb4" + b"\x01" * 36)[:ob]
        body = b"A" * p.get("pay", 0)
        hdr = struct.pack("!HHIIBBHHH", p["sport"], dport, 1, 2, off, p["flags"], p.get("win", 0), 0, 0) + opts + body
        pseudo = struct.pack("!IIBBH", src_i, dst_i, 0, 6, len(hdr))
        c = checksum(pseudo + hdr)
        return hdr[:16] + struct.pack("!H", c) + hdr[18:]
    if proto == 17:
        body = b"A" * p.get("pay", 0)
        ln = 8 + len(body)
        hdr = struct.pack("!HHHH", p["sport"], dport, ln, 0) + body
        pseudo = struct.pack("!IIBBH", src_i, dst_i, 0, 17, ln)
        c = checksum(pseudo + hdr) or 0xFFFF
        return hdr[:6] + struct.pack("!H", c) + hdr[8:]
    body = b"A" * p.get("pay", 0)
    hdr = struct.pack("!BBHHH", p.get("icmp", 8), 0, 0, 0x1234, 1) + body
    c = checksum(hdr)
    return hdr[:2] + struct.pack("!H", c) + hdr[4:]


def build_ip(p, k, src_i, dst_i):
    dport = (p.get("dport", 0) + (k if p.get("inc") else 0)) & 0xFFFF
    l4 = build_l4(p, dport, src_i, dst_i)
    ihl = p.get("ihl", 5)
    hl = ihl * 4 if ihl >= 5 else 20
    tot = hl + len(l4)
    ff = (p.get("df", 0) << 14) | (p.get("mf", 0) << 13) | (p.get("foff", 0) & 0x1FFF)
    h = struct.pack("!BBHHHBBH", 0x40 | (ihl & 0xF), 0, tot, 0x1c00 + k, ff, p["ttl"], p["proto"], 0)
    h += struct.pack("!II", src_i, dst_i)
    h = h[:10] + struct.pack("!H", checksum(h)) + h[12:] + (b"\0" * (hl - 20))
    return h + l4, dport


def golden_verdict(ipbytes):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "model"))
    import pktfeat
    import snn_int
    import json
    PA = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "model", "params.json")))
    eth = bytes.fromhex("020000000001020000000002") + b"\x08\x00" + ipbytes
    pp = pktfeat.parse(eth)
    rm = pktfeat.RateMonitor()
    s = pktfeat.encode(pp, *rm.update(*pktfeat.rate_events(pp)))
    m, c, _ = snn_int.infer(s, PA)
    return ("MALICIOUS" if m else "benign"), c


def describe(p, dport, src, dst):
    proto = {6: "TCP", 17: "UDP", 1: "ICMP"}.get(p["proto"], str(p["proto"]))
    fl = ""
    if p["proto"] == 6:
        for i, c in enumerate("FSRPAU"):
            if p["flags"] >> i & 1:
                fl += c
    return "%-4s %s > %s%s ttl=%d%s%s" % (proto, src, dst,
        (":%d" % dport) if p["proto"] in (6, 17) else "",
        p["ttl"], " [%s]" % (fl or "none") if p["proto"] == 6 else "",
        " opts=%dB" % p.get("opts", 0) if p.get("opts") else "")


def list_presets():
    print("normal:")
    for p in P:
        if not p["mal"]:
            print("  %-10s %s" % (p["name"], p["what"]))
    print("attacks:")
    for p in P:
        if p["mal"]:
            print("  %-10s %s" % (p["name"], p["what"]))
    print("special:\n  all        one of every preset\n  attacks    every attack preset")
    print("fields: ttl= sport= dport= win= opts= payload= flags=<FSRPAU> df= mf= foff= ihl= icmp= proto=tcp|udp|icmp\n"
          "        count=<n> inc=1 src=a.b.c.d\n"
          "e.g.:  sudo python3 sw/host/snn_attack.py 192.168.1.20 syn ttl=200 opts=0   # a SYN made to look like a flood")


def apply_fields(p, args):
    for a in args:
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        if k == "flags":
            p["flags"] = 0
            for ch in v.upper():
                if ch in "FSRPAU":
                    p["flags"] |= 1 << "FSRPAU".index(ch)
        elif k == "src":
            p["src"] = v
        elif k == "proto":
            p["proto"] = {"tcp": 6, "udp": 17, "icmp": 1}.get(v, int(v))
        elif k in INT_FIELDS:
            p[INT_FIELDS[k]] = int(v)
        else:
            sys.exit("unknown field '%s' (see: list)" % k)
    return p


def main():
    a = sys.argv[1:]
    dry = "--dry-run" in a
    a = [x for x in a if x != "--dry-run"]
    if len(a) < 2 or a[1] == "list":
        if a and a[0] not in ("list",) and len(a) >= 1 and a[0] != "list":
            pass
        print(__doc__.strip() + "\n")
        list_presets()
        return
    target = a[0]
    which = a[1]
    extra = a[2:]
    try:
        dst_default = ipn(target)
    except OSError:
        sys.exit("bad board IP '%s'" % target)
    my_src = None
    try:
        s0 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s0.connect((target, 9))
        my_src = s0.getsockname()[0]
        s0.close()
    except OSError:
        my_src = "192.168.1.50"

    if which == "all":
        chosen = list(P)
    elif which == "attacks":
        chosen = [p for p in P if p["mal"]]
    elif which in BY_NAME:
        chosen = [dict(BY_NAME[which])]
    else:
        sys.exit("unknown preset '%s' (see: %s %s list)" % (which, sys.argv[0], target))

    sock = None
    if not dry:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
        except PermissionError:
            sys.exit("raw sockets need root: run with sudo (or add --dry-run to only preview the verdict)")

    print("%s packets to %s (board). On the board run: ./snn_test sniff wlan0\n" % ("Previewing" if dry else "Sending", target))
    n_sent = n_mal = 0
    for p in chosen:
        if which == "all":
            p = dict(p)
            p["cnt"] = 1
        p = apply_fields(dict(p), extra)
        src = my_src if p.get("src") is None else (target if p.get("src") == "DST" else p["src"])
        dst = target
        if p.get("dst_override") == "broadcast":
            dst = target.rsplit(".", 1)[0] + ".255"
        src_i, dst_i = ipn(src), ipn(dst)
        for k in range(p.get("cnt", 1)):
            pkt, dport = build_ip(p, k, src_i, dst_i)
            verdict, cnt = golden_verdict(pkt)
            n_sent += 1
            n_mal += verdict == "MALICIOUS"
            if sock:
                try:
                    sock.sendto(pkt, (dst, 0))
                except OSError as e:
                    print("  send failed: %s" % e)
                    return
            if k == 0 or p.get("cnt", 1) <= 3:
                tag = "  <- would flash LED1" if verdict == "MALICIOUS" else ""
                print("  %-10s %-9s expect(%d:%d)  %s%s" % (p["name"], verdict, cnt[0], cnt[1], describe(p, dport, src, dst), tag))
            if sock and p.get("cnt", 1) > 1:
                time.sleep(0.003)
        if p.get("cnt", 1) > 3:
            print("  %-10s ... %d packets sent (expect %s)" % (p["name"], p["cnt"], "MALICIOUS" if p["mal"] else "benign"))
    print("\n%s %d packets; %d of them the SNN should flag as malicious." % ("previewed" if dry else "sent", n_sent, n_mal))
    if dry:
        print("drop --dry-run and run with sudo to actually send them to the board.")


if __name__ == "__main__":
    main()
