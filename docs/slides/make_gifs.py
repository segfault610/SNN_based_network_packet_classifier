#!/usr/bin/env python3
"""Animated GIFs for the docs and the slide deck, computed from the real trained network
(model/params.json) and the real test frames (sim/vectors/expected.txt) with the same
integer arithmetic as the hardware (model/snn_int.py).   Needs Pillow.
   python3 docs/slides/make_gifs.py   ->  docs/img/lif_neuron.gif, snn_frame_46_vs_47.gif, board_demo.gif"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
IMG = os.path.join(ROOT, "docs", "img")
P = json.load(open(os.path.join(ROOT, "model", "params.json")))
ROWS = [l.split() for l in open(os.path.join(ROOT, "sim", "vectors", "expected.txt")) if l.strip()]
NAMES = ["bias", "IPv4", "ARP", "IPv6", "other L3", "TCP", "UDP", "ICMP", "other L4", "IHL=5", "IHL>5", "IHL<5", "DF",
         "MF", "frag off", "TTL<=8", "TTL 9-64", "TTL 65-128", "TTL>128", "len<=40", "len 41-100", "len 101-576",
         "len 577-1500", "len>1500", "land", "bogon src", "bcast dst", "FIN", "SYN", "RST", "PSH", "ACK", "URG",
         "no flags", "dport 0", "dport 1-1023", "dport 1024-49151", "dport >=49152", "sport 0", "sport 1-1023",
         "sport 1024-49151", "sport >=49152", "doff=5", "doff>5", "doff<5", "win 0", "win small", "win large",
         "echo reply", "echo request", "unreachable", "other ICMP", "payload<=8", "payload 9-64", "payload 65-512",
         "payload>512", "len mismatch", ">=8 SYN/32", ">=16 SYN/32", ">=8 ping/32", ">=16 ping/32", "truncated",
         "sensitive port", "DNS"]

INK, PALE, AMBER, GREEN, RED, PURPLE, BLUE, GREY, WHITE, LINE = (
    "#0F2A33", "#EAF2F3", "#F2A541", "#1B998B", "#D1495B", "#7A5C99", "#2E86AB", "#5F6F78", "#FFFFFF", "#C9D6DA")


def font(size, bold=False):
    for f in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
              "/usr/share/fonts/truetype/dejavu/" + ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


F = {s: font(s) for s in (14, 16, 18, 20, 24, 28)}
FB = {s: font(s, True) for s in (14, 16, 18, 20, 24, 28, 36)}


def spikes_of(i):
    s = int(ROWS[i][0], 16)
    return [(s >> b) & 1 for b in range(64)]


def simulate(x):
    """Same integer arithmetic as model/snn_int.py, but keeps every intermediate value."""
    W1, W2, B2, th1, th2, T, leak = P["W1"], P["W2"], P["B2"], P["TH1"], P["TH2"], P["T"], P["LEAK"]
    H = len(W1[0])
    I1 = [sum(W1[i][h] for i in range(64) if x[i]) for h in range(H)]
    v1, v2, cnt = [0] * H, [0, 0], [0, 0]
    steps = []
    for t in range(T):
        pre1, s1 = [], []
        for h in range(H):
            v = v1[h] - (v1[h] >> leak) + I1[h]
            pre1.append(v)
            s1.append(int(v >= th1))
            v1[h] = 0 if v >= th1 else v
        pre2, s2 = [], []
        for o in range(2):
            I2 = B2[o] + sum(W2[h][o] for h in range(H) if s1[h])
            v = v2[o] - (v2[o] >> leak) + I2
            pre2.append(v)
            s2.append(int(v >= th2))
            if v >= th2:
                cnt[o] += 1
                v = 0
            v2[o] = v
        steps.append(dict(pre1=pre1, s1=s1, v1=list(v1), pre2=pre2, s2=s2, v2=list(v2), cnt=list(cnt)))
    mal = int(cnt[1] > cnt[0] or (cnt[1] == cnt[0] and v2[1] > v2[0]))
    return I1, steps, mal


def save(frames, path, ms):
    frames = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=ms, loop=0, optimize=True)
    print("wrote", path, len(frames), "frames", os.path.getsize(path) // 1024, "KB")


# ======================================================================= 1. one LIF neuron
def gif_lif():
    x = spikes_of(47)
    I1, steps, _ = simulate(x)
    th = P["TH1"]
    # a hidden neuron that fires a few times, so leak, integrate and fire all show
    h = max(range(16), key=lambda k: (0 < sum(s["s1"][k] for s in steps) < 8, -abs(sum(s["s1"][k] for s in steps) - 3)))
    I = I1[h]
    W, Hh = 1000, 560
    frames, durations = [], []
    hist = []                     # (t, value before firing, fired)
    v = 0
    vmax = max(th * 1.35, max(s["pre1"][h] for s in steps) * 1.1)

    def draw(phase, level, t, note, flash=False):
        im = Image.new("RGB", (W, Hh), WHITE)
        d = ImageDraw.Draw(im)
        d.text((30, 18), "One spiking neuron (LIF) in our chip: hidden neuron %d, frame 47" % h, fill=INK, font=FB[24])
        d.text((30, 54), "input current I = %d (sum of the weights of this frame's 'yes' inputs) · leak = 1/4 · threshold = %d" % (I, th),
               fill=GREY, font=F[16])
        # bucket
        bx, by, bw, bh = 60, 110, 230, 380
        d.rectangle([bx, by, bx + bw, by + bh], outline=INK, width=4)
        fill_h = int(bh * min(level, vmax) / vmax)
        col = AMBER if flash else PURPLE
        if fill_h > 0:
            d.rectangle([bx + 4, by + bh - fill_h, bx + bw - 4, by + bh - 4], fill=col)
        ty = by + bh - int(bh * th / vmax)
        d.line([bx - 20, ty, bx + bw + 20, ty], fill=RED, width=3)
        d.text((bx + bw + 25, ty - 12), "threshold %d" % th, fill=RED, font=F[16])
        d.text((bx, by + bh + 12), "charge v = %d" % level, fill=INK, font=FB[18])
        if phase == "integrate":
            d.polygon([(bx + bw / 2 - 18, by - 40), (bx + bw / 2 + 18, by - 40), (bx + bw / 2, by - 8)], fill=BLUE)
            d.text((bx + bw / 2 + 25, by - 42), "+ I", fill=BLUE, font=FB[18])
        if phase == "leak":
            d.polygon([(bx + bw - 10, by + bh - 10), (bx + bw + 30, by + bh + 5), (bx + bw + 30, by + bh - 25)], fill=BLUE)
            d.text((bx + bw + 35, by + bh - 30), "leak: lose 1/4", fill=BLUE, font=F[16])
        if flash:
            d.text((bx + 20, by + 140), "SPIKE!", fill=WHITE, font=FB[36])
        # plot
        px, py, pw, ph = 470, 120, 480, 330
        d.rectangle([px, py, px + pw, py + ph], outline=LINE, width=2)
        d.line([px, py + ph - int(ph * th / vmax), px + pw, py + ph - int(ph * th / vmax)], fill=RED, width=2)
        for k in range(8):
            xx = px + int(pw * (k + 0.5) / 8)
            d.text((xx - 10, py + ph + 6), "t%d" % (k + 1), fill=GREY, font=F[14])
        pts = []
        for (tt, val, fired) in hist:
            xx = px + int(pw * (tt + 0.5) / 8)
            yy = py + ph - int(ph * min(val, vmax) / vmax)
            pts.append((xx, yy))
            d.ellipse([xx - 7, yy - 7, xx + 7, yy + 7], fill=AMBER if fired else PURPLE)
            if fired:
                d.line([xx, py + ph, xx, py + ph + 0], fill=AMBER)
                d.text((xx - 18, yy - 30), "spike", fill="#B5761A", font=FB[14])
        if len(pts) > 1:
            d.line(pts, fill=PURPLE, width=3)
        d.text((px, py - 28), "charge at each time step (before firing)", fill=GREY, font=F[16])
        nsp = sum(1 for *_, f in hist if f)
        d.text((px, py + ph + 36), "time step %d of 8 · spikes so far: %d" % (t + 1, nsp), fill=INK, font=FB[18])
        d.text((30, Hh - 40), note, fill=INK, font=F[18])
        return im

    for t, s in enumerate(steps):
        leaked = v - (v >> P["LEAK"])
        frames.append(draw("leak", v, t, "1. leak: the charge loses a quarter (v → v − v/4)")); durations.append(600)
        frames.append(draw("leak", leaked, t, "1. leak: the charge loses a quarter (v → v − v/4)")); durations.append(500)
        pre = s["pre1"][h]
        fired = bool(s["s1"][h])
        hist.append((t, pre, fired))
        frames.append(draw("integrate", pre, t, "2. integrate: add the input current I")); durations.append(700)
        if fired:
            frames.append(draw("fire", pre, t, "3. fire: charge ≥ threshold → send a spike and reset to 0", flash=True)); durations.append(900)
            v = 0
            frames.append(draw("fire", 0, t, "3. fire: charge ≥ threshold → send a spike and reset to 0")); durations.append(500)
        else:
            frames.append(draw("none", pre, t, "3. below the threshold: no spike, keep the charge")); durations.append(600)
            v = pre
    frames.append(draw("none", v, 7, "Done: the number of spikes in 8 steps is this neuron's output for the frame")); durations.append(2500)
    frames = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    path = os.path.join(IMG, "lif_neuron.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print("wrote", path, len(frames), "frames", os.path.getsize(path) // 1024, "KB")


# ======================================================================= 2. whole network, frame 46 vs 47
def gif_network():
    W, Hh = 1100, 620
    th1, th2 = P["TH1"], P["TH2"]
    frames, durations = [], []
    for fi, label in ((46, "frame 46: a normal TCP acknowledgement"), (47, "frame 47: the first SYN-flood packet")):
        x = spikes_of(fi)
        I1, steps, mal = simulate(x)
        for t in range(-1, 8):
            im = Image.new("RGB", (W, Hh), WHITE)
            d = ImageDraw.Draw(im)
            d.text((30, 16), "Inside the SNN: " + label, fill=INK, font=FB[24])
            d.text((W - 260, 20), "start" if t < 0 else "time step %d of 8" % (t + 1), fill="#B5761A", font=FB[20])
            # inputs grid 8x8
            gx, gy, c = 30, 80, 34
            d.text((gx, gy - 4), "64 yes/no inputs", fill=GREY, font=F[16])
            for b in range(64):
                r, k = divmod(b, 8)
                x0, y0 = gx + k * c, gy + 24 + r * c
                d.rounded_rectangle([x0, y0, x0 + c - 5, y0 + c - 5], 5, fill=AMBER if x[b] else PALE)
            yes = [NAMES[b] for b in range(64) if x[b] and b]
            ty = gy + 24 + 8 * c + 10
            d.text((gx, ty), "'yes' answers:", fill=INK, font=FB[14])
            line_, yy = "", ty + 20
            for n in yes:
                if len(line_) + len(n) > 34:
                    d.text((gx, yy), line_, fill=INK, font=F[14]); yy += 18; line_ = ""
                line_ += n + " · "
            d.text((gx, yy), line_.rstrip(" ·"), fill=INK, font=F[14])
            # hidden neurons as bars
            hx, hy = 360, 110
            d.text((hx, 76), "16 hidden neurons: charge vs threshold", fill=GREY, font=F[16])
            for h in range(16):
                yb = hy + h * 28
                d.rectangle([hx, yb, hx + 300, yb + 20], outline=LINE)
                if t >= 0:
                    pre = steps[t]["pre1"][h]
                    fired = steps[t]["s1"][h]
                    frac = max(0.0, min(1.0, pre / (th1 * 1.6)))
                    if frac > 0:
                        d.rectangle([hx + 1, yb + 1, hx + 1 + int(298 * frac), yb + 19], fill=AMBER if fired else PURPLE)
                    if fired:
                        d.text((hx + 308, yb), "spike", fill="#B5761A", font=FB[14])
                d.line([hx + int(300 / 1.6), yb - 2, hx + int(300 / 1.6), yb + 22], fill=RED, width=2)
            # outputs
            ox = 760
            d.text((ox, 76), "2 output neurons", fill=GREY, font=F[16])
            for o, (nm, col) in enumerate((("benign", GREEN), ("malicious", RED))):
                yb = 130 + o * 170
                d.ellipse([ox, yb, ox + 90, yb + 90], fill=col if (t >= 0 and steps[t]["s2"][o]) else PALE, outline=col, width=4)
                d.text((ox + 105, yb + 8), nm, fill=col, font=FB[20])
                cnt = steps[t]["cnt"][o] if t >= 0 else 0
                d.text((ox + 105, yb + 40), "spikes: %d" % cnt, fill=INK, font=FB[20])
                for k in range(8):
                    on = t >= 0 and k <= t and steps[k]["s2"][o]
                    d.rectangle([ox + 105 + k * 22, yb + 72, ox + 120 + k * 22, yb + 87], fill=col if on else PALE, outline=LINE)
            if t == 7:
                verdict = ["MALICIOUS", "erase the frame"] if mal else ["BENIGN", "release the frame"]
                d.rounded_rectangle([ox - 10, 470, W - 30, 570], 12, fill=RED if mal else GREEN)
                d.text((ox + 10, 482), verdict[0], fill=WHITE, font=FB[24])
                d.text((ox + 10, 522), verdict[1], fill=WHITE, font=FB[20])
            d.text((360, Hh - 40), "purple bar = charge · amber = fires this step · red line = threshold", fill=GREY, font=F[14])
            frames.append(im)
            durations.append(1200 if t < 0 else (2600 if t == 7 else 650))
    frames = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]
    path = os.path.join(IMG, "snn_frame_46_vs_47.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print("wrote", path, len(frames), "frames", os.path.getsize(path) // 1024, "KB")


# ======================================================================= 3. the board demo
def gif_demo():
    W, Hh = 1100, 520
    frames, durations = [], []
    N = 141
    led_until = -1
    for i in range(N):
        mal, c0, c1, kind = int(ROWS[i][3]), int(ROWS[i][1]), int(ROWS[i][2]), ROWS[i][5]
        if mal:
            led_until = i + 1
        im = Image.new("RGB", (W, Hh), WHITE)
        d = ImageDraw.Draw(im)
        d.text((30, 16), "./snn_test demo on the Chameleon96: frames 0-140", fill=INK, font=FB[24])
        # LED
        lit = i <= led_until and mal
        d.ellipse([930, 20, 990, 80], fill=AMBER if lit else "#3A4A50", outline=INK, width=3)
        d.text((925, 86), "LED1", fill=INK, font=FB[16])
        # timeline
        tx, ty, tw = 30, 130, W - 60
        d.text((tx, ty - 26), "every bar = one frame · height = spikes of the winning neuron · colour = hardware verdict", fill=GREY, font=F[14])
        for k in range(i + 1):
            m, a0, a1 = int(ROWS[k][3]), int(ROWS[k][1]), int(ROWS[k][2])
            x0 = tx + int(tw * k / N)
            x1 = tx + int(tw * (k + 1) / N) - 1
            hgt = 12 * max(a0, a1)
            d.rectangle([x0, ty + 110 - hgt, x1, ty + 110], fill=RED if m else GREEN)
            if ROWS[k][5] != "benign":
                d.rectangle([x0, ty + 116, x1, ty + 124], fill=PURPLE)
        d.text((tx, ty + 130), "purple marks = frames that really are attacks (ground truth)", fill=PURPLE, font=F[14])
        x0 = tx + int(tw * 47 / N)
        if i >= 47:
            d.text((x0, ty - 6), "↓ SYN flood starts", fill=RED, font=FB[14])
        # current line, like the terminal
        verdict = "MALICIOUS" if mal else "benign"
        d.rounded_rectangle([30, 300, W - 30, 380], 10, fill=PALE)
        d.text((50, 312), "frame %3d   %-10s →  %s" % (i, kind, verdict), fill=RED if mal else INK, font=FB[24])
        d.text((50, 348), "benign neuron %d spikes, malicious neuron %d spikes (out of 8 time steps)" % (c0, c1), fill=INK, font=F[18])
        note = ""
        if i == 47:
            note = "Frame 47: bare 40-byte SYN, TTL > 128, no TCP options: a flood tool's packet. Flagged at once."
        elif i == 114:
            note = "Frame 114: a normal SYN during the flood; 'many SYNs lately' adds 1 malicious spike, benign still wins 5:1."
        elif i == 128:
            note = "Frame 128: the one miss. A flood SYN that looks like a real client (options, TTL 64): 4:2 for benign."
        elif 58 <= i <= 59 or i == 62:
            note = "Normal packets inside the flood are still let through: every frame is judged on its own header."
        if note:
            d.text((30, 410), note, fill="#B5761A", font=FB[16])
        tp = sum(1 for k in range(i + 1) if int(ROWS[k][3]) and ROWS[k][5] != "benign")
        fp = sum(1 for k in range(i + 1) if int(ROWS[k][3]) and ROWS[k][5] == "benign")
        d.text((30, Hh - 40), "so far: %d frames, %d flagged, %d false alarms" % (i + 1, tp + fp, fp), fill=GREY, font=F[16])
        frames.append(im)
        durations.append(2600 if note and i in (47, 114, 128) else (250 if i > 47 else 180))
    durations[-1] = 3000
    frames = [f.convert("P", palette=Image.ADAPTIVE, colors=32) for f in frames]
    path = os.path.join(IMG, "board_demo.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print("wrote", path, len(frames), "frames", os.path.getsize(path) // 1024, "KB")


if __name__ == "__main__":
    gif_lif()
    gif_network()
    gif_demo()
