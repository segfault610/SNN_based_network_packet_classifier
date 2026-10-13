"""
Real-traffic loader: pcap/pcapng (Ethernet) + per-packet labels from a
flow-level ground-truth CSV (UNSW-NB15 or CIC-IDS2017/2018/DDoS2019 style).

Each packet is matched to a labelled attack flow by its canonical 5-tuple
(either direction) and timestamp; unmatched packets are benign.

  UNSW-NB15  : pcaps + NUSW-NB15_GT.csv  (epoch "Start time"/"Last time")
  CIC-*      : pcaps + GeneratedLabelledFlows / TrafficLabelling CSVs
               ("Timestamp" local time dd/mm/yyyy h:mm[:ss], "Flow Duration" in us)
               CIC timestamps are local (UTC-3 for 2017) -> use --tz-offset-h 3

  python3 model/pcap_io.py capture.pcap --gt NUSW-NB15_GT.csv --format unsw --out data/unsw1.npz
  .venv/bin/python model/train.py --data data/unsw1.npz [--data more.npz ...]

The npz holds raw frames (truncated to 128 B, plus the true length), labels
and attack names, so features are recomputed by pktfeat.py (bit-exact with
the hardware, including the sliding rate window, which needs arrival order).
"""
import argparse, bisect, csv, datetime as dt, os, socket, struct, sys
import numpy as np

HDR_KEEP = 128          # bytes the hardware ever looks at


# ----------------------------------------------------------------- pcap reading
def read_pcap(path):
    """Yield (ts_seconds_float, frame_bytes, orig_len). Supports pcap and pcapng."""
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic == b"\x0a\x0d\x0d\x0a":
            yield from _read_pcapng(f)
            return
        m = struct.unpack("<I", magic)[0]
        if m in (0xA1B2C3D4, 0xA1B23C4D):
            en = "<"
        elif m in (0xD4C3B2A1, 0x4D3CB2A1):
            en = ">"
        else:
            raise ValueError("not a pcap file")
        nano = m in (0xA1B23C4D, 0x4D3CB2A1)
        hdr = f.read(20)
        if struct.unpack(en + "I", hdr[16:20])[0] != 1:
            raise ValueError("pcap link type is not Ethernet")
        while True:
            ph = f.read(16)
            if len(ph) < 16:
                return
            sec, frac, incl, orig = struct.unpack(en + "IIII", ph)
            data = f.read(incl)
            yield sec + frac * (1e-9 if nano else 1e-6), data, orig


def _read_pcapng(f):
    f.seek(0)
    en, tsres = "<", 1e-6
    while True:
        bh = f.read(8)
        if len(bh) < 8:
            return
        btype, blen = struct.unpack(en + "II", bh)
        if btype == 0x0A0D0D0A:
            bom = f.read(4)
            en = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
            blen = struct.unpack(en + "I", bh[4:])[0]
            f.read(blen - 12)
            continue
        body = f.read(blen - 8)
        if btype == 6:                                   # Enhanced Packet Block
            _, th, tl, cap, orig = struct.unpack(en + "IIIII", body[:20])
            yield ((th << 32) | tl) * tsres, body[20:20 + cap], orig
        elif btype == 1:                                 # Interface Description Block
            if struct.unpack(en + "H", body[:2])[0] != 1:
                raise ValueError("pcapng link type is not Ethernet")


# ----------------------------------------------------------------- 5-tuple
def five_tuple(fr):
    """Canonical (ip_a, port_a, ip_b, port_b, proto) or None for non-IPv4."""
    if len(fr) < 34:
        return None
    et, l3 = struct.unpack(">H", fr[12:14])[0], 14
    if et == 0x8100 and len(fr) >= 38:
        et, l3 = struct.unpack(">H", fr[16:18])[0], 18
    if et != 0x0800:
        return None
    ihl = (fr[l3] & 0xF) * 4
    proto = fr[l3 + 9]
    src, dst = fr[l3 + 12:l3 + 16], fr[l3 + 16:l3 + 20]
    sp = dp = 0
    foff = struct.unpack(">H", fr[l3 + 6:l3 + 8])[0] & 0x1FFF
    if proto in (6, 17) and foff == 0 and len(fr) >= l3 + ihl + 4:
        sp, dp = struct.unpack(">HH", fr[l3 + ihl:l3 + ihl + 4])
    a, b = (src, sp), (dst, dp)
    if a > b:
        a, b = b, a
    return (a[0], a[1], b[0], b[1], proto)


def _key(ip1, p1, ip2, p2, proto):
    a, b = (socket.inet_aton(ip1), int(p1)), (socket.inet_aton(ip2), int(p2))
    if a > b:
        a, b = b, a
    return (a[0], a[1], b[0], b[1], int(proto))


# ----------------------------------------------------------------- ground truth
class GroundTruth:
    """5-tuple -> sorted list of (start, end, attack_name)."""

    def __init__(self):
        self.idx = {}

    def add(self, key, start, end, name):
        self.idx.setdefault(key, []).append((start, end, name))

    def finish(self):
        for v in self.idx.values():
            v.sort()

    def label(self, key, ts, slack):
        lst = self.idx.get(key)
        if not lst:
            return None
        i = bisect.bisect_right(lst, (ts + slack, float("inf"), "")) - 1
        while i >= 0:
            s, e, name = lst[i]
            if s - slack <= ts <= e + slack:
                return name
            if e + slack < ts - 3600:
                break
            i -= 1
        return None


def load_unsw_gt(path):
    gt = GroundTruth()
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        r = csv.DictReader(f)
        cols = {c.strip().lower(): c for c in r.fieldnames}
        g = lambda row, n: row[cols[n]].strip()
        for row in r:
            try:
                k = _key(g(row, "source ip"), g(row, "source port") or 0, g(row, "destination ip"),
                         g(row, "destination port") or 0, PROTO.get(g(row, "protocol").lower(), -1))
            except (OSError, ValueError, KeyError):
                continue
            if k[4] < 0:
                continue
            gt.add(k, float(g(row, "start time")), float(g(row, "last time")), g(row, "attack category") or "attack")
    gt.finish()
    return gt


def load_cic_gt(paths, tz_offset_h):
    gt = GroundTruth()
    for path in paths:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            r = csv.DictReader(f)
            cols = {c.strip().lower(): c for c in r.fieldnames}
            g = lambda row, n: row[cols[n]].strip()
            for row in r:
                lab = g(row, "label")
                if lab.upper() == "BENIGN":
                    continue
                try:
                    k = _key(g(row, "source ip"), g(row, "source port"), g(row, "destination ip"),
                             g(row, "destination port"), int(g(row, "protocol")))
                    t = _cic_time(g(row, "timestamp")) + tz_offset_h * 3600
                    d = max(0.0, float(g(row, "flow duration")) / 1e6)
                except (OSError, ValueError, KeyError):
                    continue
                gt.add(k, t, t + d, lab)
    gt.finish()
    return gt


def _cic_time(s):
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M %p",
                "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            pass
    raise ValueError(s)


PROTO = {"tcp": 6, "udp": 17, "icmp": 1, "6": 6, "17": 17, "1": 1}


# ----------------------------------------------------------------- build dataset
def build(pcaps, gt, slack, max_packets=0):
    frames, lens, labels, names = [], [], [], []
    for p in pcaps:
        for ts, fr, orig in read_pcap(p):
            k = five_tuple(fr)
            name = gt.label(k, ts, slack) if k else None
            frames.append(fr[:HDR_KEEP])
            lens.append(orig)
            labels.append(1 if name else 0)
            names.append(name or "benign")
            if max_packets and len(frames) >= max_packets:
                return frames, lens, labels, names
    return frames, lens, labels, names


def save_npz(path, frames, lens, labels, names):
    buf = np.zeros((len(frames), HDR_KEEP), np.uint8)
    for i, fr in enumerate(frames):
        buf[i, :len(fr)] = np.frombuffer(fr, np.uint8)
    np.savez_compressed(path, hdr=buf, caplen=np.array([len(f) for f in frames], np.int32),
                        length=np.array(lens, np.int32), label=np.array(labels, np.int8),
                        name=np.array(names))


def load_npz(path):
    """-> list of frames (header bytes padded/truncated to true length), labels, names."""
    z = np.load(path, allow_pickle=False)
    frames = []
    for h, c, L in zip(z["hdr"], z["caplen"], z["length"]):
        fr = bytes(h[:c])
        if L > len(fr):                 # restore true length (payload bytes never inspected)
            fr = fr + bytes(L - len(fr))
        frames.append(fr)
    return frames, z["label"].astype(int), z["name"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pcap", nargs="+")
    ap.add_argument("--gt", nargs="+", required=True, help="ground-truth CSV file(s)")
    ap.add_argument("--format", choices=["unsw", "cic"], required=True)
    ap.add_argument("--tz-offset-h", type=float, default=0.0, help="hours added to CIC local timestamps")
    ap.add_argument("--slack", type=float, default=1.0, help="time tolerance (s)")
    ap.add_argument("--max-packets", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    gt = load_unsw_gt(a.gt[0]) if a.format == "unsw" else load_cic_gt(a.gt, a.tz_offset_h)
    print(f"ground truth: {sum(len(v) for v in gt.idx.values())} attack flows")
    fr, ln, lab, nm = build(a.pcap, gt, a.slack, a.max_packets)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    save_npz(a.out, fr, ln, lab, nm)
    from collections import Counter
    print(f"{len(fr)} packets, {sum(lab)} malicious -> {a.out}")
    print(Counter(nm).most_common(15))


if __name__ == "__main__":
    main()
