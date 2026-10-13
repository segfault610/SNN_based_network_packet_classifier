# Innovus 3/7: power rings, stripes, follow-pins (sroute).
source scripts/innovus_setup.tcl
addRing \
    -nets "$VDD_NET $VSS_NET" \
    -type core_rings \
    -follow core \
    -layer [list top $RING_H bottom $RING_H left $RING_V right $RING_V] \
    -width 2 \
    -spacing 2 \
    -offset 2

addStripe \
    -nets "$VDD_NET $VSS_NET" \
    -direction vertical \
    -layer $STRIPE_V \
    -width 1 \
    -spacing 1 \
    -set_to_set_distance 40 \
    -start_from left

addStripe \
    -nets "$VDD_NET $VSS_NET" \
    -direction horizontal \
    -layer $STRIPE_H \
    -width 1 \
    -spacing 1 \
    -set_to_set_distance 40 \
    -start_from bottom

sroute \
    -nets "$VDD_NET $VSS_NET" \
    -connect {corePin blockPin padPin floatingStripe} \
    -layerChangeRange $PG_LAYERS \
    -allowJogging true \
    -allowLayerChange true

verifyConnectivity -type special -nets "$VDD_NET $VSS_NET" > $RPT_DIR/powerplan_pg_connectivity.rpt
checkDesign -all > $RPT_DIR/powerplan_checkdesign.rpt
defOut -floorplan $PNR_DIR/${DESIGN}_floorplan.def
save_stage powerplan
