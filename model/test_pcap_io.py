"""Self-test of the real-data path without real data: synthetic stream -> pcap +
UNSW-style ground-truth CSV -> pcap_io -> identical frames/labels/features."""
import csv, os, struct, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import gen_traffic, pktfeat, pcap_io

def main():
    stream = gen_traffic.Gen(11).stream(3000, quiet=(10, 60))
    d = tempfile.mkdtemp()
    pc, gtp = os.path.join(d, "t.pcap"), os.path.join(d, "gt.csv")
    t0 = 1_500_000_000.0
    flows = {}
    with open(pc, "wb") as f:
        f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for i, (fr, lab, kind) in enumerate(stream):
            ts = t0 + i * 0.001
            f.write(struct.pack("<IIII", int(ts), int((ts % 1) * 1e6), len(fr), len(fr)) + fr)
            k = pcap_io.five_tuple(fr)
            if lab and k:
                s, e, _ = flows.get(k, (ts, ts, kind))
                flows[k] = (min(s, ts), max(e, ts), kind)
    with open(gtp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Start time", "Last time", "Attack category", "Protocol", "Source IP", "Source Port",
                    "Destination IP", "Destination Port"])
        for (a, pa, b, pb, pr), (s, e, kind) in flows.items():
            w.writerow([s, e, kind, {6: "tcp", 17: "udp", 1: "icmp"}.get(pr, str(pr)),
                        ".".join(map(str, a)), pa, ".".join(map(str, b)), pb])
    gt = pcap_io.load_unsw_gt(gtp)
    fr, ln, lab, nm = pcap_io.build([pc], gt, slack=0.0005)
    npz = os.path.join(d, "t.npz")
    pcap_io.save_npz(npz, fr, ln, lab, nm)
    frames2, lab2, _ = pcap_io.load_npz(npz)
    ref = pktfeat.encode_stream([f for f, _, _ in stream])
    got = pktfeat.encode_stream(frames2)
    truth = [l for _, l, _ in stream]
    has_tuple = [pcap_io.five_tuple(f) is not None for f, _, _ in stream]
    lab_ok = sum(int(a == b) for a, b, h in zip(lab2, truth, has_tuple) if h) / sum(has_tuple)
    print(f"features identical after pcap round trip (128B header + true length): {ref == got}")
    print(f"label agreement on IPv4 packets: {lab_ok:.4f}  (malicious: truth {sum(truth)}, recovered {int(sum(lab2))})")
    ok = ref == got and lab_ok > 0.99
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
