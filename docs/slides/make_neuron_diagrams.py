#!/usr/bin/env python3
"""RTL-Viewer-style SVG datapath diagrams + activation GIFs for the neuron HDL doc.
   python3 docs/slides/make_neuron_diagrams.py   ->  docs/img/neuron_*.svg, neuron_activation.gif, neuron_datapath.gif
Needs Pillow for the GIFs; the SVGs need nothing.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img")
INK, REG, OP, MUX, CMP, WIRE, RED, GREEN, AMBER, PURPLE, GREY, PALE = (
    "#0F2A33", "#D6E8F5", "#FCE6C8", "#E7DBF0", "#FBD9DE", "#45606B", "#D1495B", "#1B998B", "#F2A541", "#7A5C99", "#5F6F78", "#EAF2F3")
MONO = "font-family='DejaVu Sans Mono,monospace'"
SANS = "font-family='DejaVu Sans,Arial,sans-serif'"


# ---------------------------------------------------------------- tiny SVG builder (RTL-viewer look)
class SVG:
    def __init__(self, w, h, title):
        self.w, self.h = w, h
        self.e = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" %s>' % (w, h, SANS),
                  '<rect width="%d" height="%d" fill="white"/>' % (w, h),
                  '<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
                  'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker></defs>' % WIRE,
                  '<text x="%d" y="34" font-size="26" font-weight="bold" fill="%s">%s</text>' % (24, INK, title)]

    def reg(self, x, y, w, h, label, sub="", fill=REG):
        """register: rounded box with a clock triangle (bottom-left)."""
        self.e.append('<rect x="%d" y="%d" width="%d" height="%d" rx="7" fill="%s" stroke="%s" stroke-width="2"/>'
                      % (x, y, w, h, fill, INK))
        self.e.append('<path d="M%d,%d l10,-8 l0,16 z" fill="%s"/>' % (x + 2, y + h - 8, INK))  # clk notch
        self.text(x + w / 2, y + h / 2 - (7 if sub else 0), label, 16, bold=True)
        if sub:
            self.text(x + w / 2, y + h / 2 + 11, sub, 12, fill=GREY)
        return (x, y, w, h)

    def op(self, cx, cy, sym, r=22, fill=OP):
        """arithmetic operator: circle with a symbol (+ - >>)."""
        self.e.append('<circle cx="%d" cy="%d" r="%d" fill="%s" stroke="%s" stroke-width="2"/>' % (cx, cy, r, fill, INK))
        self.text(cx, cy, sym, 18, bold=True)
        return (cx, cy, r)

    def box(self, x, y, w, h, label, sub="", fill=OP):
        self.e.append('<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="%s" stroke="%s" stroke-width="2"/>'
                      % (x, y, w, h, fill, INK))
        self.text(x + w / 2, y + h / 2 - (7 if sub else 0), label, 15, bold=True)
        if sub:
            self.text(x + w / 2, y + h / 2 + 11, sub, 11, fill=GREY)
        return (x, y, w, h)

    def mux(self, x, y, w, h, label="mux", sub=""):
        """trapezoid multiplexer."""
        self.e.append('<path d="M%d,%d L%d,%d L%d,%d L%d,%d z" fill="%s" stroke="%s" stroke-width="2"/>'
                      % (x, y, x + w, y + 14, x + w, y + h - 14, x, y + h, MUX, INK))
        self.text(x + w / 2 + 4, y + h / 2 - (7 if sub else 0), label, 14, bold=True)
        if sub:
            self.text(x + w / 2 + 4, y + h / 2 + 11, sub, 11, fill=GREY)
        return (x, y, w, h)

    def cmp(self, x, y, w, h, label):
        self.e.append('<path d="M%d,%d L%d,%d L%d,%d L%d,%d z" fill="%s" stroke="%s" stroke-width="2"/>'
                      % (x, y, x + w - 16, y, x + w, y + h / 2, x + w - 16, y + h) if False else
                      '<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="%s" stroke="%s" stroke-width="2"/>'
                      % (x, y, w, h, CMP, INK))
        self.text(x + w / 2, y + h / 2, label, 16, bold=True)
        return (x, y, w, h)

    def port(self, x, y, label, side="l"):
        self.e.append('<circle cx="%d" cy="%d" r="4" fill="%s"/>' % (x, y, INK))
        self.text(x + (14 if side == "l" else -14), y, label, 14, fill=INK,
                  anchor="start" if side == "l" else "end", mono=True)

    def wire(self, pts, arrow=True, color=WIRE, w=2.2, dash=False):
        d = "M" + " L".join("%d,%d" % (x, y) for x, y in pts)
        da = ' stroke-dasharray="6,4"' if dash else ""
        mk = ' marker-end="url(#a)"' if arrow else ""
        self.e.append('<path d="%s" fill="none" stroke="%s" stroke-width="%s"%s%s/>' % (d, color, w, da, mk))

    def wlabel(self, x, y, t, fill=GREY):
        self.text(x, y, t, 12, fill=fill, mono=True)

    def text(self, x, y, t, size, bold=False, fill=INK, anchor="middle", mono=False):
        b = " font-weight='bold'" if bold else ""
        self.e.append("<text x='%d' y='%d' font-size='%d' fill='%s' text-anchor='%s' dominant-baseline='middle'%s %s>%s</text>"
                      % (x, y, size, fill, anchor, b, MONO if mono else "", t.replace("&", "&amp;").replace("<", "&lt;")))

    def note(self, x, y, lines, fill=GREY):
        for i, ln in enumerate(lines):
            self.text(x, y + i * 18, ln, 13, fill=fill, anchor="start")

    def save(self, name):
        self.e.append("</svg>")
        open(os.path.join(IMG, name), "w").write("\n".join(self.e))
        print("wrote", name)


# ---------------------------------------------------------------- our LIF neuron datapath
def lif_datapath():
    s = SVG(1120, 470, "LIF neuron datapath (one of 16, inside snn_core.v)")
    yc = 250
    s.port(30, yc, "acc = I", "l")          # input current
    s.port(30, 150, "th1", "l")             # threshold
    vx = 150
    s.reg(vx, yc - 30, 110, 60, "v", "20-bit charge", fill=PURPLE if False else REG)
    # shift tap
    sh = s.box(330, 120, 100, 44, ">> 2", "(wires only)", fill=PALE)
    sub = s.op(500, 190, "−")          # v - (v>>2)
    add = s.op(620, yc, "+")                # + I
    cmpb = s.cmp(720, yc - 28, 110, 56, "≥ th1")
    spike = s.reg(900, yc - 30, 120, 60, "spike", "1 bit, registered", fill=AMBER)
    muxb = s.mux(620, 330, 120, 70, "mux", "spike?0:v")
    s.port(1090, yc, "to layer 2", "r")
    # wires
    s.wire([(260, yc), (300, yc)])                              # v out
    s.wire([(300, yc), (300, 142), (330, 142)])                # v -> shift
    s.wire([(430, 142), (478, 142), (478, 178)])               # shift -> sub (b)
    s.wire([(300, yc), (300, 202), (478, 202)])                # v -> sub (a)
    s.wlabel(305, yc - 12, "v")
    s.wire([(522, 190), (560, 190), (560, yc - 10), (598, yc - 10)])  # sub -> add
    s.wire([(60, yc), (90, yc), (90, 300), (585, 300), (585, yc + 12), (598, yc + 12)])   # I -> add via bottom
    s.wlabel(120, 294, "I = sum of weights of active inputs")
    s.wire([(642, yc), (720, yc)])                             # add -> cmp
    s.wlabel(650, yc - 12, "v_next")
    s.wire([(830, yc), (900, yc)])                             # cmp -> spike reg
    s.wire([(960, yc + 30), (960, 430), (240, 430), (240, yc + 30)], color=GREEN, dash=True)  # feedback to mux/reg via... simplified
    # better feedback: v_next and spike -> mux -> v
    s.wire([(642, yc + 12), (670, yc + 12), (670, 330)], color=GREY)          # v_next -> mux data
    s.wire([(776, yc + 8), (900, yc + 8)], arrow=False, color=WIRE)
    s.wire([(900, 300), (760, 300), (760, 358)], color=AMBER)                 # spike -> mux select
    s.wlabel(766, 345, "select", fill="#B5761A")
    s.wire([(620, 365), (215, 365), (215, yc + 30)], color=GREEN)             # mux -> v (feedback)
    s.wlabel(300, 352, "new charge written back every clock (one LIF step)", fill=GREEN)
    s.wire([(70, 150), (665, 150), (665, 232)], color=GREY, w=1.8)            # th1 -> cmp
    s.wlabel(80, 142, "threshold")
    s.wire([(1020, yc), (1090, yc)])
    s.note(24, 452 - 6, ["register (holds state)  ⬤ operator (add / subtract)  ▭ shift = wiring  "
                         "▭ compare  ⬢ mux  — green = feedback path"])
    s.save("neuron_lif_datapath.svg")


# ---------------------------------------------------------------- the 4-state controller
def fsm():
    s = SVG(1120, 360, "snn_core.v controller: 4 states per frame")
    ys = 150
    xs = [120, 400, 680, 960]
    names = [("IDLE", "wait for a\nspike vector"), ("ACC", "1 clock per\n'yes' input"),
             ("LIF", "8 time steps\n(leak, add, fire)"), ("OUT", "compare counts,\nreport verdict")]
    for i, (x, (nm, sub)) in enumerate(zip(xs, names)):
        fill = AMBER if nm == "LIF" else (GREEN if nm == "OUT" else REG)
        s.e.append('<circle cx="%d" cy="%d" r="62" fill="%s" stroke="%s" stroke-width="2.5"/>' % (x, ys, fill, INK))
        s.text(x, ys - 8, nm, 20, bold=True)
        for j, ln in enumerate(sub.split("\n")):
            s.text(x, ys + 12 + j * 15, ln, 12, fill=GREY)
        if i < 3:
            s.wire([(x + 62, ys), (xs[i + 1] - 62, ys)])
    # LIF self loop x8
    s.e.append('<path d="M%d,%d a40,34 0 1,1 60,0" fill="none" stroke="%s" stroke-width="2.2" marker-end="url(#a)"/>'
               % (xs[2] - 30, ys - 60, AMBER))
    s.text(xs[2] + 0, ys - 120, "x8", 16, bold=True, fill="#B5761A")
    s.wire([(xs[3], ys + 62), (xs[3], 300), (xs[0], 300), (xs[0], ys + 62)], color=GREY, dash=True)
    s.text(560, 318, "next frame", 13, fill=GREY)
    s.save("neuron_fsm.svg")


# ---------------------------------------------------------------- alternative neuron datapaths (schematic)
def alt(name, title, blocks, note, extra_badge=None):
    s = SVG(1120, 330, title)
    yc = 175
    s.port(30, yc, "inputs I", "l")
    x = 130
    prev = (60, yc)
    for b in blocks:
        kind, label, sub = b[0], b[1], b[2] if len(b) > 2 else ""
        w = b[3] if len(b) > 3 else 120
        if kind == "reg":
            s.reg(x, yc - 30, w, 60, label, sub, fill=b[4] if len(b) > 4 else REG)
            box = (x, yc - 30, w, 60)
        elif kind == "op":
            s.op(x + 24, yc, label, fill=b[4] if len(b) > 4 else OP)
            box = (x, yc - 24, 48, 48); w = 48
        elif kind == "cmp":
            s.cmp(x, yc - 28, w, 56, label)
            box = (x, yc - 28, w, 56)
        else:
            s.box(x, yc - 28, w, 56, label, sub, fill=b[4] if len(b) > 4 else OP)
            box = (x, yc - 28, w, 56)
        s.wire([(prev[0], yc), (x, yc)])
        prev = (x + w, yc)
        x += w + 60
    s.port(1090, yc, "spike", "r")
    s.wire([(prev[0], yc), (1090, yc)])
    if extra_badge:
        s.e.append('<rect x="%d" y="60" width="300" height="40" rx="8" fill="%s"/>' % (790, extra_badge[1]))
        s.text(940, 80, extra_badge[0], 15, bold=True, fill="white")
    s.note(30, 290, note)
    s.save(name)


def alternatives():
    alt("neuron_if.svg", "IF neuron (integrate-and-fire): the simplest",
        [("reg", "v", "charge"), ("op", "+", ""), ("cmp", "≥ th", "")],
        ["No leak: the charge only ever goes up until it fires. 1 register + 1 adder + 1 comparator.",
         "Cheapest to build, but it never forgets, so noise can slowly push it over the line."])
    alt("neuron_lif.svg", "LIF neuron (ours): leaky integrate-and-fire",
        [("reg", "v", "charge"), ("box", ">>2 then −", "leak", 130, PALE), ("op", "+", ""), ("cmp", "≥ th", "")],
        ["Adds a leak (lose 1/4 each step) before integrating. register + 2 adders + compare + reset mux.",
         "The standard choice: forgets old input, so it reacts to recent activity. This is what our chip uses."])
    alt("neuron_alif.svg", "Adaptive LIF (ALIF): threshold that rises after firing",
        [("reg", "v", "charge"), ("box", ">>2 then −", "leak", 130, PALE), ("op", "+", ""),
         ("cmp", "≥ th*", ""), ("reg", "th*", "adaptive", 110, "#FDE7B8")],
        ["Extra register + adder: each spike raises the threshold, which then decays. Longer memory.",
         "Helps with slow scans and bursts that a fixed threshold would miss. ~1 more register per neuron."],
        extra_badge=("+1 register, +1 adder vs LIF", PURPLE))
    alt("neuron_ttfs.svg", "Time-to-first-spike (TTFS): fire once, encode WHEN",
        [("reg", "v", "charge"), ("box", "leak", "", 90, PALE), ("op", "+", ""), ("cmp", "≥ th", ""),
         ("reg", "timer", "latch t", 110, "#FDE7B8")],
        ["LIF plus a small timer and a 'fired' latch: the neuron spikes at most once and the time carries the value.",
         "Far fewer spike events -> lower switching power, at the cost of a timer per neuron (Zhou & Li 2020)."],
        extra_badge=("fires at most ONCE per frame", GREEN))
    # Izhikevich: two coupled registers + a multiplier (the costly part)
    s = SVG(1120, 360, "Izhikevich neuron: biologically rich, but needs a multiplier")
    yc = 180
    s.port(30, yc, "inputs I", "l")
    s.reg(150, yc - 30, 110, 60, "v", "membrane")
    mul = s.box(330, 120, 120, 56, "v x v", "MULTIPLIER", fill=RED)
    s.text(390, 100, "the expensive part", 13, fill=RED, bold=True)
    s.box(330, 220, 120, 56, "0.04v²+5v+140", "poly", fill=OP)
    s.op(560, yc, "+")
    s.reg(680, 70, 110, 60, "u", "recovery", fill="#FDE7B8")
    s.op(560, 90, "−")
    s.cmp(700, yc - 28, 120, 56, "≥ 30 mV")
    s.reg(900, yc - 30, 110, 60, "spike", "+ reset v,u", fill=AMBER)
    s.wire([(60, yc), (150, yc)])
    s.wire([(260, yc), (300, yc), (300, 148), (330, 148)])
    s.wire([(260, yc), (300, yc), (300, 248), (330, 248)], arrow=False)
    s.wire([(450, 148), (520, 148), (520, 80)])
    s.wire([(450, 248), (520, 248), (520, yc + 8), (536, yc + 8)])
    s.wire([(584, yc), (700, yc)])
    s.wire([(680, 100), (584, 100)])
    s.wire([(820, yc), (900, yc)])
    s.wire([(955, yc + 30), (955, 320), (205, 320), (205, yc + 30)], color=GREEN, dash=True)
    s.text(560, 338, "v and u fed back each step", 13, fill=GREEN)
    s.e.append('<rect x="620" y="300" width="470" height="40" rx="8" fill="%s"/>' % RED)
    s.text(855, 320, "2 registers + a multiplier: several x the area of LIF", 15, bold=True, fill="white")
    s.save("neuron_izhikevich.svg")
    # Binary MLP neuron (not spiking) - N3IC style
    s = SVG(1120, 330, "Binary MLP neuron (not spiking): XNOR + popcount, one pass")
    yc = 170
    s.port(30, yc, "inputs (bits)", "l")
    s.box(160, yc - 40, 150, 80, "XNOR array", "input ⊕ weight", fill=OP)
    s.box(400, yc - 40, 160, 80, "popcount", "count the 1s", fill=PALE)
    s.cmp(640, yc - 28, 130, 56, "≥ half?")
    s.reg(840, yc - 30, 120, 60, "output", "1 bit", fill=AMBER)
    s.wire([(60, yc), (160, yc)])
    s.wire([(310, yc), (400, yc)])
    s.wire([(560, yc), (640, yc)])
    s.wire([(770, yc), (840, yc)])
    s.port(1090, yc, "to next layer", "r")
    s.wire([(960, yc), (1090, yc)])
    s.e.append('<rect x="160" y="250" width="800" height="40" rx="8" fill="%s"/>' % GREEN)
    s.text(560, 270, "No register, no time steps: one pass, no state. Fast, but no temporal memory.", 15, bold=True, fill="white")
    s.save("neuron_binary_mlp.svg")


# ---------------------------------------------------------------- GIF: activation (addresses the mental model)
def font(sz, b=False):
    for f in (("DejaVuSans-Bold.ttf" if b else "DejaVuSans.ttf"),
              "/usr/share/fonts/truetype/dejavu/" + ("DejaVuSans-Bold.ttf" if b else "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def hx(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def activation_gif():
    """Two input neurons send spikes into one LIF neuron; it charges, leaks, fires a spike onward, resets.
    Makes clear: leak = internal decay; what goes to the next layer is the FIRED spike, not the leaked charge."""
    W, H = 1040, 560
    ink, reg_c, am, gr, rd, pu, grey = hx(INK), hx(REG), hx(AMBER), hx(GREEN), hx(RED), hx(PURPLE), hx(GREY)
    th, leak_sh = 256, 2
    # a little script of events across 11 steps
    I = 150
    frames, durs = [], []
    v = 0
    hist = []
    vmax = th * 1.4

    def draw(stage, v_now, t, incoming, fired, note):
        im = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(im)
        d.text((24, 18), "How a neuron activates: integrate, leak, fire", ink, font=font(26, True))
        # input neurons (left)
        for i, cy in enumerate((150, 300)):
            on = incoming and i in incoming
            d.ellipse([60, cy - 26, 112, cy + 26], fill=am if on else reg_c, outline=ink, width=3)
            d.text((50, cy + 32), "input %d" % (i + 1), grey, font=font(13), anchor="ma")
            # wire to the body
            col = am if on else (210, 220, 224)
            d.line([112, cy, 300, 225], fill=col, width=5 if on else 2)
            if on:
                # moving spike dot
                frac = {"arrive": 0.9}.get(stage, 0.5)
                px, py = 112 + (300 - 112) * frac, cy + (225 - cy) * frac
                d.ellipse([px - 9, py - 9, px + 9, py + 9], fill=am, outline=ink, width=2)
                d.text(((112 + 300) / 2, (cy + 225) / 2 - 20), "+weight", (181, 118, 26), font=font(14, True), anchor="mm")
        # the neuron body as a bucket
        bx, by, bw, bh = 300, 110, 150, 230
        d.rounded_rectangle([bx, by, bx + bw, by + bh], 10, outline=ink, width=4)
        fillh = int((bh - 8) * min(v_now, vmax) / vmax)
        col = am if fired else pu
        if fillh > 0:
            d.rectangle([bx + 4, by + bh - 4 - fillh, bx + bw - 4, by + bh - 4], fill=col)
        ty = by + bh - int((bh - 8) * th / vmax)
        d.line([bx - 16, ty, bx + bw + 16, ty], fill=rd, width=3)
        d.text((bx + bw + 22, ty), "threshold", rd, font=font(13), anchor="lm")
        d.text((bx + bw / 2, by - 14), "neuron: charge v = %d" % v_now, ink, font=font(16, True), anchor="mm")
        # leak arrow (drains OUT, not to next neuron)
        if stage == "leak":
            d.polygon([(bx + bw - 6, by + bh - 20), (bx + bw + 34, by + bh - 6), (bx + bw + 34, by + bh - 34)], fill=(90, 130, 150))
            d.text((bx + bw + 40, by + bh - 20), "leak: lose 1/4\n(drains away)", (90, 130, 150), font=font(13), anchor="lm")
        # output neuron (right) + spike travelling only when fired
        ox, oy = 820, 225
        lit = fired or (stage == "send")
        d.ellipse([ox - 30, oy - 30, ox + 30, oy + 30], fill=gr if lit else reg_c, outline=ink, width=3)
        d.text((ox, oy + 42), "next layer", grey, font=font(13), anchor="ma")
        d.line([bx + bw, 225, ox - 30, oy], fill=am if stage == "send" else (210, 220, 224), width=5 if stage == "send" else 2)
        if stage == "send":
            d.ellipse([ox - 90 - 9, oy - 9, ox - 90 + 9, oy + 9], fill=am, outline=ink, width=2)
            d.text(((bx + bw + ox) / 2, oy - 22), "FIRED spike travels on", (27, 95, 70), font=font(15, True), anchor="mm")
        # charge-over-time plot
        px, py, pw, ph = 540, 90, 260, 150
        d.rectangle([px, py, px + pw, py + ph], outline=(201, 214, 218), width=2)
        d.line([px, py + ph - int(ph * th / vmax), px + pw, py + ph - int(ph * th / vmax)], fill=rd, width=2)
        pts = []
        for (tt, val, fr) in hist:
            xx = px + int(pw * (tt + 0.5) / 11)
            yy = py + ph - int(ph * min(val, vmax) / vmax)
            pts.append((xx, yy))
            d.ellipse([xx - 5, yy - 5, xx + 5, yy + 5], fill=am if fr else pu)
        if len(pts) > 1:
            d.line(pts, fill=pu, width=3)
        d.text((px, py - 16), "charge over time (each dot = one step)", grey, font=font(13), anchor="lm")
        d.text((px, py + ph + 18), "amber dot = the neuron fired that step", (181, 118, 26), font=font(13), anchor="lm")
        # stage caption
        d.rounded_rectangle([24, 470, W - 24, 540], 10, fill=hx(PALE))
        d.text((44, 490), {"arrive": "1. INTEGRATE", "leak": "2. LEAK", "fire": "3. FIRE", "send": "3. FIRE",
                           "idle": "resting"}.get(stage, ""), ink, font=font(18, True))
        d.text((210, 492), note, ink, font=font(16))
        return im

    events = [
        ("arrive", [0, 1], "two input spikes arrive; each adds its weight to the charge"),
        ("leak", None, "every step the charge loses a quarter of itself (it drains away, it is NOT sent on)"),
        ("arrive", [0], "another input spike adds more charge"),
        ("leak", None, "leak again: a little of the charge is lost"),
        ("arrive", [0, 1], "more spikes; the charge is now near the threshold line"),
        ("fire", None, "charge crossed the threshold!"),
        ("send", None, "the neuron FIRES: a 1-bit spike travels to the next layer"),
        ("idle", None, "...and the charge resets to 0, ready to start again"),
    ]
    for t, (stage, inc, note) in enumerate(events):
        if stage == "arrive":
            v = v - (v >> leak_sh) + I + (I if inc and len(inc) > 1 else 0)
        elif stage == "leak":
            v = v - (v >> leak_sh)
        fired = stage in ("fire", "send")
        if stage == "fire":
            hist.append((t, v, True))
        elif stage not in ("send", "idle"):
            hist.append((t, v, False))
        frames.append(draw(stage, 0 if stage == "idle" else v, t, inc, fired, note))
        durs.append(1700 if stage in ("fire", "send") else 1300)
        if stage == "send":
            v = 0
    frames.append(draw("idle", 0, 8, None, False, "the cycle repeats for every time step and every frame"))
    durs.append(2600)
    frames = [f.convert("P", palette=Image.ADAPTIVE, colors=48) for f in frames]
    path = os.path.join(IMG, "neuron_activation.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durs, loop=0, optimize=True)
    print("wrote neuron_activation.gif", os.path.getsize(path) // 1024, "KB")


# ---------------------------------------------------------------- GIF: the HDL datapath carrying values
def datapath_gif():
    """The LIF datapath (register -> shift -> subtract -> add -> compare -> mux) with the real numbers
    flowing through it for a few time steps, so the hardware and the behaviour line up."""
    W, H = 1040, 460
    ink, reg_c, grey = hx(INK), hx(REG), hx(GREY)
    th, I = 256, 225
    frames, durs = [], []
    v = 0

    def node(d, x, y, w, h, label, val, active):
        fill = hx(AMBER) if active else reg_c
        d.rounded_rectangle([x, y, x + w, y + h], 7, fill=fill, outline=ink, width=2)
        d.text((x + w / 2, y + 18), label, ink, font=font(15, True), anchor="mm")
        if val is not None:
            d.text((x + w / 2, y + h - 16), str(val), hx(PURPLE), font=font(16, True), anchor="mm")

    def draw(t, stage):
        im = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(im)
        d.text((24, 16), "LIF datapath carrying real values (hidden neuron, I=%d, th=%d)" % (I, th), ink, font=font(20, True))
        leaked = v - (v >> 2)
        vnext = leaked + I
        fired = vnext >= th
        y = 150
        node(d, 60, y, 150, 70, "v register", v, stage == "reg")
        node(d, 300, 60, 130, 60, ">>2 (leak)", v >> 2, stage == "leak")
        node(d, 300, y, 150, 70, "subtract", leaked, stage == "leak")
        node(d, 520, y, 130, 70, "+ I", vnext, stage == "add")
        node(d, 710, y, 150, 70, "compare >=th", "SPIKE" if fired else "no", stage == "cmp")
        node(d, 710, 300, 150, 60, "reset mux", 0 if fired else vnext, stage == "mux")
        # wires
        for a, b in [((210, y + 35), (300, y + 35)), ((450, y + 35), (520, y + 35)),
                     ((650, y + 35), (710, y + 35))]:
            d.line([a, b], fill=hx(WIRE), width=3)
        d.line([(230, y), (230, 90), (300, 90)], fill=hx(WIRE), width=2)   # v -> shift
        d.line([(785, y + 70), (785, 300)], fill=hx(AMBER) if fired else hx(WIRE), width=2)
        d.line([(710, 330), (135, 330), (135, y + 70)], fill=hx(GREEN), width=3)  # feedback
        d.text((400, 350), "new charge written back to v (one time step)", hx(GREEN), font=font(14), anchor="mm")
        d.rounded_rectangle([24, 395, W - 24, 445], 8, fill=hx(PALE))
        d.text((44, 420), "step %d/8   %s" % (t + 1, {"reg": "read v", "leak": "leak: v - v/4",
                "add": "add input current I", "cmp": "charge >= threshold?  " + ("FIRE" if fired else "no spike"),
                "mux": "write back: 0 if it fired, else v"}[stage]), ink, font=font(16, True), anchor="lm")
        return im, fired

    for t in range(4):
        for stage in ("reg", "leak", "add", "cmp", "mux"):
            im, fired = draw(t, stage)
            frames.append(im)
            durs.append(900 if stage in ("cmp", "mux") else 700)
        v = 0 if (v - (v >> 2) + I) >= th else (v - (v >> 2) + I)
    frames = [f.convert("P", palette=Image.ADAPTIVE, colors=48) for f in frames]
    path = os.path.join(IMG, "neuron_datapath.gif")
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durs, loop=0, optimize=True)
    print("wrote neuron_datapath.gif", os.path.getsize(path) // 1024, "KB")


if __name__ == "__main__":
    lif_datapath()
    fsm()
    alternatives()
    activation_gif()
    datapath_gif()
