# Colour every placed cell of a GDS by type (flip-flop / combinational / buffer) -> PNG.
#   python cell_map.py <design.gds> <out.png>      (pip install klayout numpy pillow)
import sys, re, numpy as np
import klayout.db as db
from PIL import Image, ImageDraw, ImageFont
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.top_cell()
dbu = ly.dbu; bb = top.bbox(); W = H = 1600
sx = W / bb.width(); sy = H / bb.height()
img = np.full((H, W, 3), 255, np.uint8)
CLS = [("seq",   re.compile(r"__(e?dfx|dfr|dfs|dfb|dlx|dlr|sdf)"), (21, 101, 192)),
       ("buf",   re.compile(r"__(buf|clkbuf|clkinv|clkdly|dlygate|dlymetal)"), (158, 158, 158)),
       ("tap",   re.compile(r"__(tap|decap|fill|diode)"),       None),
       ("comb",  re.compile(r"."),                              (255, 143, 0))]
count = {c[0]: 0 for c in CLS}; area = {c[0]: 0.0 for c in CLS}
for inst in top.each_inst():
    name = inst.cell.name
    for cname, rx, col in CLS:
        if rx.search(name):
            b = inst.bbox(); count[cname] += 1; area[cname] += b.width() * b.height() * dbu * dbu
            if col:
                x0 = int((b.left - bb.left) * sx); x1 = max(x0 + 1, int((b.right - bb.left) * sx))
                y0 = int((bb.top - b.top) * sy);  y1 = max(y0 + 1, int((bb.top - b.bottom) * sy))
                img[y0:y1, x0:x1] = col
            break
im = Image.fromarray(img); d = ImageDraw.Draw(im)
try: f = ImageFont.truetype("DejaVuSans.ttf", 28)
except Exception: f = ImageFont.load_default()
legend = [("flip-flops (W1 weights, neuron state, FIFOs)", (21,101,192)), ("combinational logic", (255,143,0)),
          ("buffers: clock tree, timing and hold repair", (158,158,158))]
pad = 140; out = Image.new("RGB", (W, H + pad), "white"); out.paste(im, (0, 0)); d = ImageDraw.Draw(out)
for i, (t, c) in enumerate(legend):
    x = 20 + (i % 2) * 800; y = H + 20 + (i // 2) * 55
    d.rectangle([x, y, x + 36, y + 36], fill=c); d.text((x + 50, y + 2), t, fill="black", font=f)
out.save(sys.argv[2]); print(count); print({k: round(v) for k, v in area.items()}); print("die um", bb.width()*dbu, bb.height()*dbu)
