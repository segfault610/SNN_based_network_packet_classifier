#!/usr/bin/env python3
"""Software stand-in for the Tang Nano 9K bitstream on a pseudo-terminal, for
testing tang_demo.py without hardware. Speaks the same SLIP protocol and
classifies with the golden model, rebuilding weights from the config writes.
  python3 sw/host/fake_tang.py      -> prints the /dev/pts/N to pass as --port"""
import os, pty, struct, sys, tty
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "model"))
import pktfeat, snn_int

END, ESC, ESC_END, ESC_ESC = 0xC0, 0xDB, 0xDC, 0xDD
s8 = lambda v: v - 256 if v & 0x80 else v


def slip(m):
    o = bytearray()
    for b in m:
        o += bytes([ESC, ESC_END]) if b == END else bytes([ESC, ESC_ESC]) if b == ESC else bytes([b])
    return bytes(o) + bytes([END])


def main():
    master, slave = pty.openpty()
    tty.setraw(slave)
    print(os.ttyname(slave), flush=True)
    regs = {0: 1}
    W1 = [[0] * 16 for _ in range(64)]
    rm = pktfeat.RateMonitor()
    st = [0] * 5
    buf, esc = bytearray(), False
    while True:
        data = os.read(master, 4096)
        out = bytearray()
        for b in data:
            if not esc and b == END:
                m, buf = bytes(buf), bytearray()
                if not m:
                    continue
                if m[0] == ord("C") and len(m) == 7:
                    a, d = struct.unpack(">HI", m[1:])
                    regs[a] = d
                    if 0x100 <= a < 0x200:
                        row, lane = (a - 0x100) >> 2, a & 3
                        for k in range(4):
                            W1[row][4 * lane + k] = s8((d >> (8 * k)) & 0xFF)
                elif m[0] == ord("R") and len(m) == 3:
                    a = struct.unpack(">H", m[1:])[0]
                    v = st[a - 0x20] if 0x20 <= a <= 0x24 else regs.get(a, 0)
                    out += slip(b"r" + struct.pack(">I", v))
                elif m[0] == ord("P"):
                    fr = m[1:]
                    p = pktfeat.parse(fr)
                    spk = pktfeat.encode(p, *rm.update(*pktfeat.rate_events(p)))
                    P = dict(W1=W1, W2=[[s8(regs.get(0x10 + h, 0) & 0xFF), s8((regs.get(0x10 + h, 0) >> 8) & 0xFF)] for h in range(16)],
                             B2=[s8(regs.get(4, 0) & 0xFF), s8((regs.get(4, 0) >> 8) & 0xFF)],
                             TH1=regs.get(1, 256), TH2=regs.get(2, 128), T=regs.get(3, 0x28) & 0xF, LEAK=(regs.get(3, 0x28) >> 4) & 3)
                    mal = snn_int.infer(spk, P)[0]
                    st[0] += 1; st[2] += mal
                    out += slip(bytes([ord("V"), mal << 7]))
                    if mal and regs.get(0, 1) & 1:
                        st[4] += 1
                    else:
                        st[3] += 1
                        out += slip(b"F" + fr)
            elif not esc and b == ESC:
                esc = True
            else:
                buf.append((END if b == ESC_END else ESC) if esc else b)
                esc = False
        if out:
            os.write(master, bytes(out))


if __name__ == "__main__":
    main()
