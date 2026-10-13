#!/usr/bin/env python3
"""
Tang Nano 9K in-line SNN firewall demo (host side).

  python3 sw/host/tang_demo.py --port /dev/ttyUSB1                 # golden vectors + check
  python3 sw/host/tang_demo.py --port /dev/ttyUSB1 --pcap cap.pcap # replay any capture
  python3 sw/host/tang_demo.py --port /dev/ttyUSB1 --monitor       # CTRL.drop_en = 0

Protocol: see fpga/tang9k/tang9k_snn_top.v (SLIP, 1 Mbaud 8N1).
"""
import argparse, os, struct, sys, time
import serial

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
VEC = os.path.join(ROOT, "sim", "vectors")
END, ESC, ESC_END, ESC_ESC = 0xC0, 0xDB, 0xDC, 0xDD


def slip(msg):
    out = bytearray()
    for b in msg:
        out += bytes([ESC, ESC_END]) if b == END else bytes([ESC, ESC_ESC]) if b == ESC else bytes([b])
    return bytes(out) + bytes([END])


class Link:
    def __init__(self, port, baud):
        self.s = serial.Serial(port, baud, timeout=0)
        self.buf, self.esc, self.msgs = bytearray(), False, []

    def send(self, msg):
        self.s.write(slip(msg))

    def poll(self):
        for b in self.s.read(4096):
            if not self.esc and b == END:
                if self.buf:
                    self.msgs.append(bytes(self.buf))
                self.buf = bytearray()
            elif not self.esc and b == ESC:
                self.esc = True
            else:
                self.buf.append((END if b == ESC_END else ESC) if self.esc else b)
                self.esc = False
        m, self.msgs = self.msgs, []
        return m

    def cfg_write(self, a, d):
        self.send(b"C" + struct.pack(">HI", a, d & 0xFFFFFFFF))

    def cfg_read(self, a, timeout=1.0):
        self.send(b"R" + struct.pack(">H", a))
        t = time.time()
        while time.time() - t < timeout:
            for m in self.poll():
                if m[:1] == b"r":
                    return struct.unpack(">I", m[1:5])[0]
        raise TimeoutError("no response from FPGA (port/baud? bitstream loaded?)")


def read_pcap(path):
    with open(path, "rb") as f:
        hdr = f.read(24)
        magic = struct.unpack("<I", hdr[:4])[0]
        en = "<" if magic in (0xA1B2C3D4, 0xA1B23C4D) else ">"
        if struct.unpack(en + "I", hdr[20:24])[0] != 1:
            sys.exit("pcap link type is not Ethernet")
        while True:
            ph = f.read(16)
            if len(ph) < 16:
                return
            incl = struct.unpack(en + "IIII", ph)[2]
            yield f.read(incl)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=1_000_000)
    ap.add_argument("--cfg", default=os.path.join(VEC, "cfg.txt"))
    ap.add_argument("--frames", default=os.path.join(VEC, "frames.txt"))
    ap.add_argument("--expected", default=os.path.join(VEC, "expected.txt"))
    ap.add_argument("--pcap")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--window", type=int, default=8)
    ap.add_argument("--monitor", action="store_true", help="classify only, forward everything")
    a = ap.parse_args()

    L = Link(a.port, a.baud)
    time.sleep(0.1); L.poll()
    n = 0
    for line in open(a.cfg):
        ad, d = line.split()
        L.cfg_write(int(ad, 16), int(d, 16)); n += 1
    L.cfg_write(0x000, 0 if a.monitor else 1)
    th1 = L.cfg_read(0x001)
    print(f"link OK, {n} config words written, TH1 readback = {th1}")

    if a.pcap:
        frames, exp = list(read_pcap(a.pcap)), None
    else:
        frames = [bytes(int(x, 16) for x in l.split()[1:]) for l in open(a.frames)]
        exp = [l.split() for l in open(a.expected)]
    if a.max:
        frames = frames[:a.max]

    fwd, verd = [], []
    sent, t0 = 0, time.time()
    while len(verd) < len(frames) or len(fwd) + sum(verd) < len(verd) and time.time() - t0 < 600:
        for m in L.poll():
            if m[:1] == b"F":
                fwd.append(m[1:])
            elif m[:1] == b"V":
                mal = m[1] >> 7
                verd.append(mal)
                i = len(verd) - 1
                kind = exp[i][5] if exp else ""
                print(f"#{i:5d} {len(frames[i]):5d}B {'MALICIOUS -> dropped' if mal and not a.monitor else 'malicious (monitor)' if mal else 'benign    -> forwarded'} {kind}")
        done = len(fwd) + (0 if a.monitor else sum(verd))
        if sent < len(frames) and sent - done < a.window:
            L.send(b"P" + frames[sent]); sent += 1
        elif sent == len(frames) and len(verd) == len(frames):
            time.sleep(0.2); continue
        else:
            time.sleep(0.0005)
        if time.time() - t0 > 600:
            break
    for m in L.poll():
        if m[:1] == b"F":
            fwd.append(m[1:])
    dt = time.time() - t0
    stats = [L.cfg_read(0x020 + i) for i in range(5)]
    print(f"\n{len(frames)} frames in {dt:.1f}s: {sum(verd)} malicious, {len(fwd)} forwarded")
    print("HW counters committed/dropped_ingress/malicious/forwarded/blocked:", stats)
    if exp:
        em = [int(e[3]) for e in exp[:len(frames)]]
        lab = [int(e[4]) for e in exp[:len(frames)]]
        bitexact = verd == em
        want = [frames[i] for i in range(len(frames)) if not em[i] or a.monitor]
        tp = sum(v and l for v, l in zip(verd, lab)); fp = sum(v and not l for v, l in zip(verd, lab))
        print(f"verdicts bit-exact vs golden model: {bitexact};  forwarded frames identical: {fwd == want}")
        print(f"detection vs labels: TP={tp} FP={fp} FN={sum(lab)-tp} TN={len(lab)-sum(lab)-fp}")
        print("RESULT:", "PASS" if bitexact and fwd == want else "FAIL")


if __name__ == "__main__":
    main()
