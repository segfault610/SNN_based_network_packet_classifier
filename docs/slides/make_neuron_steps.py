#!/usr/bin/env python3
"""Six clean step pictures of how a LIF neuron activates, for docs/neuron_hdl.md (no GIFs).
   python3 docs/slides/make_neuron_steps.py  ->  docs/img/neuron_step1..6.png"""
import os
from PIL import Image, ImageDraw, ImageFont

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img")
INK, PALE, AMBER, GREEN, RED, PURPLE, GREY, REG = (
    (15, 42, 51), (234, 242, 243), (242, 165, 65), (27, 153, 139), (209, 73, 91), (122, 92, 153), (95, 111, 120), (214, 232, 245))
TH = 256


def F(sz, b=False):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if b else ""),
              "DejaVuSans-Bold.ttf" if b else "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def pic(n, title, v, inputs_on, fired, sent, caption, vmax=380):
    W, H = 960, 430
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([14, 14, W - 14, 70], 10, fill=INK)
    d.text((34, 42), "Step %d:  %s" % (n, title), "white", font=F(24, True), anchor="lm")
    # input neurons
    for i, cy in enumerate((150, 270)):
        on = i in inputs_on
        d.ellipse([60, cy - 28, 116, cy + 28], fill=AMBER if on else REG, outline=INK, width=3)
        d.text((88, cy), "in%d" % (i + 1), INK, font=F(15, True), anchor="mm")
        col = AMBER if on else (205, 216, 221)
        d.line([116, cy, 300, 240], fill=col, width=6 if on else 2)
        if on:
            px, py = 220, cy + (240 - cy) * (220 - 116) / (300 - 116)
            d.ellipse([px - 11, py - 11, px + 11, py + 11], fill=AMBER, outline=INK, width=2)
            d.text((200, cy + (240 - cy) * 0.35 - 22), "+ weight", (181, 118, 26), font=F(15, True), anchor="mm")
    # the neuron bucket
    bx, by, bw, bh = 300, 110, 150, 260
    d.rounded_rectangle([bx, by, bx + bw, by + bh], 12, outline=INK, width=4)
    fh = int((bh - 10) * min(v, vmax) / vmax)
    if fh > 0:
        d.rectangle([bx + 5, by + bh - 5 - fh, bx + bw - 5, by + bh - 5], fill=AMBER if fired else PURPLE)
    ty = by + bh - int((bh - 10) * TH / vmax)
    d.line([bx - 18, ty, bx + bw + 18, ty], fill=RED, width=3)
    d.text((bx + bw + 24, ty), "threshold", RED, font=F(15, True), anchor="lm")
    d.text((bx + bw / 2, by - 16), "neuron  v = %d" % v, INK, font=F(17, True), anchor="mm")
    # leak arrow
    if n == 3:
        d.polygon([(bx + bw - 4, by + bh - 36), (bx + bw + 42, by + bh - 18), (bx + bw + 42, by + bh - 54)], fill=(90, 130, 150))
        d.text((bx + bw + 48, by + bh - 36), "leaks out", (90, 130, 150), font=F(15, True), anchor="lm")
    # output neuron + travelling spike
    ox, oy = 820, 240
    lit = fired or sent
    d.ellipse([ox - 32, oy - 32, ox + 32, oy + 32], fill=GREEN if lit else REG, outline=INK, width=3)
    d.text((ox, oy), "next", "white" if lit else INK, font=F(15, True), anchor="mm")
    d.line([bx + bw, 240, ox - 32, oy], fill=AMBER if sent else (205, 216, 221), width=6 if sent else 2)
    if sent:
        d.ellipse([640 - 11, oy - 11, 640 + 11, oy + 11], fill=AMBER, outline=INK, width=2)
        d.text(((bx + bw + ox) / 2, oy - 24), "FIRED spike travels on", (27, 95, 70), font=F(16, True), anchor="mm")
    # caption
    d.rounded_rectangle([14, 388, W - 14, 420], 8, fill=PALE)
    d.text((W / 2, 404), caption, INK, font=F(15), anchor="mm")
    im.save(os.path.join(IMG, "neuron_step%d.png" % n))
    print("wrote neuron_step%d.png" % n)


leak = lambda x: x - (x >> 2)
pic(1, "resting", 0, [], False, False, "The neuron starts empty. Charge v = 0. Two inputs feed it from the previous layer.")
v = leak(0) + 150 + 150
pic(2, "integrate", v, [0, 1], False, False, "Two input spikes arrive. Each adds its weight to the charge: v climbs toward the threshold.")
v2 = leak(v)
pic(3, "leak", v2, [], False, False, "Next step: the neuron loses a quarter of its OWN charge. It drains away — it is NOT sent onward.")
v3 = leak(v2) + 150
pic(4, "integrate again", v3, [0], False, False, "Another input spike adds more charge. Now v is just under the threshold line.")
v4 = leak(v3) + 150
pic(5, "fire", v4, [0], True, False, "Charge crosses the threshold! The neuron fires a single 1-bit spike (and will reset to 0).")
pic(6, "spike travels, then reset", 0, [], False, True, "The FIRED spike is what reaches the next layer. The charge resets to 0, ready to start again.")
