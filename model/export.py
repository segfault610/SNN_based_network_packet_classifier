"""
Export trained parameters + golden test vectors for the RTL testbench.

  sim/vectors/cfg.txt       "<addr_hex> <data_hex>" config-bus writes (weights, thresholds)
  sim/vectors/snn_fw.bin    same, binary LE u32 pairs for the kernel module (/lib/firmware)
  sim/vectors/w1.hex        W1 rows for $readmemh (W1_INIT, FPGA ROM init)
  sim/vectors/frames.txt    "<len> <b0> <b1> ..." one frame per line (hex bytes)
  sim/vectors/expected.txt  "<spikes64_hex> <cnt0> <cnt1> <mal> <label>" per frame

Usage: .venv/bin/python model/export.py [n_frames] [seed]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import gen_traffic, pktfeat, snn_int

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "sim", "vectors")


def u8(v):
    return v & 0xFF


def w1_row_hex(P, row):
    H = P["N_HID"]
    v = 0
    for h in range(H):
        v |= u8(P["W1"][row][h]) << (8 * h)
    return f"{v:0{H*2}x}"


def cfg_writes(P):
    H = P["N_HID"]
    w = [(0x001, P["TH1"]), (0x002, P["TH2"]), (0x003, (P["LEAK"] << 4) | P["T"]),
         (0x004, (u8(P["B2"][1]) << 8) | u8(P["B2"][0]))]
    for h in range(H):
        w.append((0x010 + h, (u8(P["W2"][h][1]) << 8) | u8(P["W2"][h][0])))
    for row in range(pktfeat.N_IN):
        for lane in range(H // 4):
            v = 0
            for k in range(4):
                v |= u8(P["W1"][row][4 * lane + k]) << (8 * k)
            w.append((0x100 + 4 * row + lane, v))
    return w


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    P = json.load(open(os.path.join(os.path.dirname(__file__), "params.json")))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "cfg.txt"), "w") as f:
        for a, d in cfg_writes(P):
            f.write(f"{a:03x} {d:08x}\n")
    # firmware blob for sw/cv96/kmod/snn_fw.ko (/lib/firmware/snn_fw.bin): LE u32 (addr, data) pairs
    import struct
    with open(os.path.join(OUT, "snn_fw.bin"), "wb") as f:
        for a, d in cfg_writes(P):
            f.write(struct.pack("<II", a, d))
    with open(os.path.join(OUT, "w1.hex"), "w") as f:
        for row in range(pktfeat.N_IN):
            f.write(w1_row_hex(P, row) + "\n")
    stream = gen_traffic.Gen(seed).stream(n, quiet=(10, 60))
    frames = [fr for fr, _, _ in stream]
    spk = pktfeat.encode_stream(frames)
    nmal = agree = 0
    with open(os.path.join(OUT, "frames.txt"), "w") as ff, open(os.path.join(OUT, "expected.txt"), "w") as fe:
        for (fr, lab, kind), s in zip(stream, spk):
            mal, cnt, _ = snn_int.infer(s, P)
            ff.write(f"{len(fr)} " + " ".join(f"{b:02x}" for b in fr) + "\n")
            fe.write(f"{pktfeat.spikes_to_int(s):016x} {cnt[0]} {cnt[1]} {mal} {lab} {kind}\n")
            nmal += mal
            agree += int(mal == lab)
    print(f"exported {n} frames (seed {seed}): {nmal} predicted malicious, "
          f"{sum(l for _, l, _ in stream)} labelled malicious, model accuracy on this set {agree/n:.4f}")


if __name__ == "__main__":
    main()
