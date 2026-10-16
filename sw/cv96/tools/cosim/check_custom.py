#!/usr/bin/env python3
"""Cross-check snn_test's custom-traffic modes (craft / frame / pcap) against the golden model.

Runs snn_test on the accelerator RTL (Verilator co-simulation, ./run_cosim.sh) with 'hex', so every
classified frame's bytes are printed, then recomputes each verdict independently with
model/pktfeat.py + model/snn_int.py over the same frame sequence (same 32-frame SYN/ping window).
Any difference is printed and the script exits non-zero.

   .venv/bin/python sw/cv96/tools/cosim/check_custom.py
"""
import json
import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "..", "..")
sys.path.insert(0, os.path.join(ROOT, "model"))
import pktfeat  # noqa: E402
import snn_int  # noqa: E402

P = json.load(open(os.path.join(ROOT, "model", "params.json")))
LINE = re.compile(r"^\s*(\d+)\s+(MALICIOUS|benign)\s+\((\d+):(\d+)\)")


def run(args):
    out = subprocess.run([os.path.join(HERE, "run_cosim.sh")] + args + ["hex"], capture_output=True, text=True).stdout
    res, cur = [], None
    for ln in out.splitlines():
        m = LINE.match(ln)
        if m:
            cur = [int(m.group(2) == "MALICIOUS"), int(m.group(3)), int(m.group(4))]
        elif ln.strip().startswith("hex:") and cur is not None:
            cur.append(bytes(int(x, 16) for x in ln.split()[1:]))
            res.append(cur)
            cur = None
    return res, out


def golden(frames_with_len):
    """frames_with_len: [(bytes, true_len)] in order, starting from an empty rate window."""
    rm = pktfeat.RateMonitor()
    out = []
    for fr, true_len in frames_with_len:
        p = pktfeat.parse(fr[:128])
        p["flen"] = true_len                    # the hardware gets the true length in SUBMIT
        s = pktfeat.encode(p, *rm.update(*pktfeat.rate_events(p)))
        mal, cnt, _ = snn_int.infer(s, P)
        out.append((mal, cnt[0], cnt[1]))
    return out


def check(name, args, true_lens=None):
    res, raw = run(args)
    if not res:
        print("  %-38s NO OUTPUT\n%s" % (name, raw[-800:]))
        return 1
    seq = [(r[3], (true_lens[i] if true_lens else len(r[3]))) for i, r in enumerate(res)]
    exp = golden(seq)
    bad = [(i, tuple(r[:3]), e) for i, (r, e) in enumerate(zip(res, exp)) if tuple(r[:3]) != e]
    nmal = sum(r[0] for r in res)
    print("  %-38s %4d frames, %3d malicious: %s" % (name, len(res), nmal, "OK, identical to the golden model" if not bad else "%d MISMATCHES" % len(bad)))
    for i, hw, e in bad[:5]:
        print("      frame %d: hardware %s, golden %s" % (i + 1, hw, e))
    return len(bad)


def write_pcap(path, frames, link=1):
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHiIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, link))
        for k, fr in enumerate(frames):
            if link == 113:                      # Linux cooked: 16-byte header, EtherType at 14
                fr = struct.pack("!HHH8sH", 0, 1, 6, b"\x02\x00\x00\x00\x00\x01\x00\x00", int.from_bytes(fr[12:14], "big")) + fr[14:]
            f.write(struct.pack("<IIII", 1000 + k, 0, len(fr), len(fr)) + fr)


def main():
    vec = [bytes(int(x, 16) for x in l.split()[1:]) for l in open(os.path.join(ROOT, "sim", "vectors", "frames.txt")) if l.strip()]
    bad = 0
    print("snn_test custom modes on the RTL vs the golden model:")
    bad += check("craft all (22 presets)", ["craft", "all"])
    bad += check("craft synflood (40 packets)", ["craft", "synflood"])
    bad += check("craft xmas count=40 (port scan)", ["craft", "xmas", "count=40"])
    bad += check("craft pingflood count=30", ["craft", "pingflood", "count=30"])
    bad += check("craft syn ttl=200 opts=0 win=512", ["craft", "syn", "ttl=200", "opts=0", "win=512"])
    bad += check("craft synflood ttl=64 opts=12 count=5", ["craft", "synflood", "ttl=64", "opts=12", "win=64240", "count=5"])
    bad += check("craft ack flags=SF dport=22", ["craft", "ack", "flags=SF", "dport=22"])
    bad += check("craft dns dport=0 payload=900", ["craft", "dns", "dport=0", "payload=900"])
    bad += check("frame <hex of test frame 47>", ["frame", vec[47].hex()])
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "eth.pcap")
        write_pcap(p1, vec[:200])
        bad += check("pcap: test frames 0-199 (Ethernet)", ["pcap", p1])
        p2 = os.path.join(td, "sll.pcap")
        write_pcap(p2, vec[40:100], link=113)
        bad += check("pcap: frames 40-99 (Linux cooked)", ["pcap", p2], true_lens=[len(f) for f in vec[40:100]])
    print("RESULT:", "PASS" if bad == 0 else "FAIL (%d mismatches)" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
