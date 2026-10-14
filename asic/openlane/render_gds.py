# Render a sky130 GDS to PNG, showing only the physical layers (diffusion, poly, li1, met1-met5).
# Marker / boundary layers are hidden: drawn as solid fill they cover the whole die.
#   KLayout:  klayout -zz -rd gds=<file.gds> -rd out=<file.png> -r render_gds.py
#   Python:   python render_gds.py <file.gds> <file.png>      (pip install klayout)
import sys

try:
    import pya as lay                                   # inside the KLayout application
except ImportError:
    import klayout.lay as lay                           # pip package

if "gds" not in globals():
    gds, out = sys.argv[1], sys.argv[2]

# sky130 GDS (layer, datatype) -> colour, drawn bottom to top
LAYERS = [
    ((65, 20), 0x2E7D32, "diff"),  ((66, 20), 0xC62828, "poly"), ((67, 20), 0x8E24AA, "li1"),
    ((68, 20), 0x1565C0, "met1"),  ((69, 20), 0xEF6C00, "met2"), ((70, 20), 0x00897B, "met3"),
    ((71, 20), 0x6D4C41, "met4"),  ((72, 20), 0x546E7A, "met5"),
]
COLOR = {k: c for k, c, _ in LAYERS}

lv = lay.LayoutView()
lv.load_layout(gds, True)
lv.max_hier()
it = lv.begin_layers()
while not it.at_end():
    lp = it.current()
    p = lp.dup()
    key = (lp.source_layer, lp.source_datatype)
    if key in COLOR:
        p.visible = True
        p.fill_color = p.frame_color = COLOR[key]
        p.dither_pattern = 5          # light hatch so lower layers stay visible
        p.transparent = True
    else:
        p.visible = False
    lv.set_layer_properties(it, p)
    it.next()
lv.set_config("background-color", "#ffffff")
lv.set_config("grid-visible", "false")
lv.zoom_fit()
lv.save_image(out, 2000, 2000)
print("wrote", out)
