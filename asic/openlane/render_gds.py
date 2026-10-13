# KLayout batch script: render a GDS to PNG.
#   klayout -zz -rd gds=<file.gds> -rd out=<file.png> [-rd lyp=<layer props>] -r render_gds.py
import pya

lv = pya.LayoutView()
lv.load_layout(gds, True)
try:
    if lyp:
        lv.load_layer_props(lyp)
except NameError:
    pass
lv.max_hier()
lv.set_config("background-color", "#ffffff")
lv.set_config("grid-visible", "false")
lv.zoom_fit()
lv.save_image(out, 2000, 2000)
print("wrote", out)
