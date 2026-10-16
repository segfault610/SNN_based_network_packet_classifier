#!/usr/bin/env python3
"""Explain the SNN's decision for one Ethernet frame: what it reads, the 64 yes/no answers, the spike
counts, and which answers pushed the decision (golden model = the FPGA, bit for bit).

  .venv/bin/python model/explain_frame.py <hex bytes>              e.g. the 'hex:' line printed by snn_test
  .venv/bin/python model/explain_frame.py --vector 47              frame 47 of sim/vectors/frames.txt
  .venv/bin/python model/explain_frame.py --pcap cap.pcap --index 3

The 32-frame SYN/ping memory starts empty, as after 'snn_test craft/frame' (use --syn N --ping N to
pretend N SYNs / pings were seen in the last 32 frames).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pktfeat  # noqa: E402
import snn_int  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
P = json.load(open(os.path.join(ROOT, "model", "params.json")))


def load(args):
    if args.vector is not None:
        lines = [l.split() for l in open(os.path.join(ROOT, "sim", "vectors", "frames.txt")) if l.strip()]
        return bytes(int(x, 16) for x in lines[args.vector][1:])
    if args.pcap:
        import pcap_io
        for k, (_, fr, _) in enumerate(pcap_io.read_pcap(args.pcap)):
            if k == args.index:
                return fr
        sys.exit("pcap has fewer than %d frames" % (args.index + 1))
    hx = "".join(c for c in " ".join(args.hex) if c in "0123456789abcdefABCDEF")
    return bytes.fromhex(hx)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hex", nargs="*")
    ap.add_argument("--vector", type=int)
    ap.add_argument("--pcap")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--syn", type=int, default=0, help="SYNs seen in the last 32 frames")
    ap.add_argument("--ping", type=int, default=0, help="pings seen in the last 32 frames")
    args = ap.parse_args()
    fr = load(args)
    if len(fr) < 14:
        sys.exit("need at least an Ethernet header (14 bytes)")

    p = pktfeat.parse(fr)
    rm = pktfeat.RateMonitor()
    for k in range(32):                           # pretend history for the rate window
        rm.update(k < args.syn, k < args.ping)
    is_syn, is_echo = pktfeat.rate_events(p)
    syn_c, ping_c = rm.update(is_syn, is_echo)
    s = pktfeat.encode(p, syn_c, ping_c)
    mal, cnt, v2 = snn_int.infer(s, P)

    print("frame: %d bytes; the FPGA receives the first %d bytes and the true length" % (len(fr), min(len(fr), 128)))
    print("parsed: " + ", ".join("%s=%s" % (k, v) for k, v in p.items() if k not in ("l3",)))
    print("rate window: %d SYNs and %d pings in the last 32 frames (this one included)" % (syn_c, ping_c))
    yes = [i for i in range(64) if s[i]]
    print("\n'yes' answers (%d of 64):" % len(yes))
    for i in yes:
        print("  %2d  %s" % (i, pktfeat.FEATURE_NAMES[i]))
    print("\noutput spikes in 8 time steps: benign %d, malicious %d  ->  %s" % (cnt[0], cnt[1], "MALICIOUS" if mal else "benign"))

    # Which answers mattered: switch each 'yes' off and see how the evidence moves. Evidence = charge the
    # malicious output neuron accumulated minus the benign one's (spikes x threshold + leftover charge);
    # unlike the spike count (max 8) it does not saturate.
    th2 = P["TH2"]

    def evidence(c, v):
        return (c[1] * th2 + v[1]) - (c[0] * th2 + v[0])

    base = evidence(cnt, v2)
    effect = []
    for i in yes:
        if i == 0:
            continue
        t = list(s)
        t[i] = 0
        m2, c2, w2 = snn_int.infer(t, P)
        effect.append((base - evidence(c2, w2), i, m2 != mal, c2))
    effect.sort(key=lambda e: -abs(e[0]))
    print("\nwhat drove the decision (each 'yes' switched off in turn; + = it pushed towards MALICIOUS):")
    for d, i, flips, c2 in effect:
        if d == 0:
            continue
        print("  %+6d  %-14s %s%s" % (d, pktfeat.FEATURE_NAMES[i], "towards MALICIOUS" if d > 0 else "towards benign",
              "   <- alone flips the verdict (would be %d:%d)" % (c2[0], c2[1]) if flips else ""))
    if all(e[0] == 0 for e in effect):
        print("  no single answer changes the evidence: the decision rests on the combination")


if __name__ == "__main__":
    main()
