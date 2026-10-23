#!/usr/bin/env python3
"""Review deck: the single spiking neuron, in hardware (basics + LIF + comparison + citations).
   python3 docs/slides/make_review_deck.py  ->  docs/SNN_Neuron_Review.pptx"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deck_lib import *  # noqa

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
IMG = os.path.join(DOCS, "img")
TMP = "/tmp"
OUT = os.path.join(DOCS, "SNN_Neuron_Review.pptx")

d = Deck()
S1 = "The single neuron"


def section(num, name, blurb, notes):
    s = d.slide(dark=True, notes=notes)
    badge(s, 0.6, 2.4, str(num), d=1.0, size=34)
    text(s, 1.9, 2.3, 10.6, 1.1, name, 38, WHITE, bold=True, font=HEAD, anchor="m")
    text(s, 1.9, 3.5, 10.2, 1.3, blurb, 18, "B9CBD0")
    return s


def cite(s, x, y, w, refs, size=12):
    text(s, x, y, w, 0.5, [[("Refs: ", {"bold": True, "color": GREY}), (refs, {"color": GREY, "italic": True})]], size=size, color=GREY)


# ===================================================== 1 title
s = d.slide(dark=True, notes="Review deck. Focus: what a single spiking neuron is, how LIF works, how it is built in "
            "hardware, how it compares with other neuron models, and why it fits an in-NIC packet classifier.")
for i, (cx, cy, c) in enumerate([(10.4, 1.3, AMBER), (11.4, 2.1, GREEN), (10.7, 3.2, AMBER), (11.9, 3.7, RED), (10.1, 4.4, AMBER)]):
    badge(s, cx, cy, "", fill=c, d=0.5 if i % 2 else 0.62)
for a, b in [((10.7, 1.6), (11.6, 2.3)), ((11.6, 2.3), (11.0, 3.5)), ((11.0, 3.5), (12.1, 3.9)), ((11.0, 3.5), (10.4, 4.7))]:
    line(s, a[0], a[1], b[0], b[1], color="3E6A75", width=2)
text(s, 0.6, 1.7, 9.2, 1.9, "The spiking neuron,\nin hardware", 46, WHITE, bold=True, font=HEAD)
text(s, 0.6, 3.9, 8.8, 1.2, "What a neuron is, what LIF means, how it is built in logic, and why it fits a "
     "line-rate packet classifier", 20, "B9CBD0")
text(s, 0.6, 6.3, 9, 0.4, "SNN-based network packet classifier · review", 14, "8FA8AF")

# ===================================================== 2 roadmap
s = d.slide(notes="We build from the bottom: one neuron first, then compare neuron models, then the network, the "
            "hardware, and the numbers against the literature.")
title(s, "What this review covers")
parts = [("1", "A neuron", "biological idea → artificial neuron → the spiking neuron", AMBER),
         ("2", "LIF", "leak, integrate, fire; the model our chip uses", GREEN),
         ("3", "In hardware", "one neuron as a logic diagram; the real RTL", BLUE),
         ("4", "Vs other models", "IF, ALIF, TTFS, Izhikevich — and why LIF fits", PURPLE),
         ("5", "Numbers", "power & area, compared with the literature", RED)]
for i, (n, h, b, c) in enumerate(parts):
    x = 0.6 + i * 2.48
    box(s, x, 1.8, 2.3, 4.5, fill=PALE)
    badge(s, x + 0.2, 2.0, n, fill=c, color=WHITE if c != AMBER else INK, d=0.65, size=22)
    text(s, x + 0.2, 2.85, 1.95, 0.9, h, 19, INK, bold=True, font=HEAD)
    text(s, x + 0.2, 3.75, 1.95, 2.3, b, 14, INK)

# ===================================================== 3 what is a neuron
s = d.slide(section=S1, notes="A neuron is a tiny decision unit. A biological neuron collects electrical charge from "
            "its inputs and fires a pulse when charged enough. An artificial neuron copies this: inputs times weights, "
            "summed, passed through a function.")
title(s, "What is a neuron?", sub="The basic decision unit of every neural network")
box(s, 0.6, 1.7, 5.9, 4.7, fill=PALE)
text(s, 0.9, 1.9, 5.4, 0.5, "Biological", 20, GREEN, bold=True, font=HEAD)
bullets(s, 0.9, 2.5, 5.3, 3.6, [
    "Dendrites collect electrical charge from other neurons",
    "The cell body adds it up",
    "When the charge passes a threshold, the neuron fires a short pulse (a spike) down its axon",
    "Then it resets and starts again"], size=15)
box(s, 6.85, 1.7, 5.9, 4.7, fill=PALE)
text(s, 7.15, 1.9, 5.4, 0.5, "Artificial (what we build)", 20, BLUE, bold=True, font=HEAD)
box(s, 7.3, 2.5, 5.1, 0.8, fill=WHITE, line=BLUE, line_w=2, txt="output = f( Σ wᵢ · xᵢ + b )", size=18, font="Cambria")
bullets(s, 7.15, 3.5, 5.4, 2.8, [
    [("Inputs xᵢ ", {"bold": True}), ("× weights wᵢ, summed", {})],
    [("Weights ", {"bold": True}), ("are what training learns", {})],
    [("A function f ", {"bold": True}), ("decides the output", {})],
    "A standard (ANN) neuron outputs one number"], size=15)

# ===================================================== 4 spiking neuron
s = d.slide(section=S1, notes="A spiking neuron is the brain-like version. Instead of one number, it works over time "
            "and outputs short 1/0 pulses, spikes. Inputs are also spikes. This is what makes the hardware cheap: a "
            "weight times a 1-bit spike is just add-the-weight-or-not, no multiplier.")
title(s, "The spiking neuron: pulses, not numbers")
for col, (hd, c, lines_) in enumerate([
        ("Standard neuron", BLUE, ["Outputs one number (e.g. 0.73)", "Inputs are numbers",
                                   "Needs multiplications", "No sense of time / no memory"]),
        ("Spiking neuron (ours)", AMBER, ["Outputs spikes: 1 or 0 at each time step", "Inputs are spikes too",
                                          "Weight × spike = add the weight, or not", "Keeps a charge over time (memory)"])]):
    x = 0.6 + col * 6.25
    box(s, x, 1.65, 5.9, 4.3, fill=PALE)
    text(s, x + 0.3, 1.85, 5.4, 0.5, hd, 21, c if c != AMBER else "B5761A", bold=True, font=HEAD)
    bullets(s, x + 0.3, 2.55, 5.4, 3.2, lines_, size=16)
box(s, 0.6, 6.15, 12.15, 0.7, fill=INK, txt=[[("Key point:  ", {"bold": True, "color": AMBER}),
    ("because inputs are 1-bit spikes, a spiking neuron needs NO multipliers — only adders. That is why it is cheap in silicon.", {"color": WHITE})]], size=15)

# ===================================================== 5 LIF step pictures
s = d.slide(section=S1, notes="LIF = Leaky Integrate-and-Fire. The leaky bucket: inputs pour charge in (integrate), a "
            "quarter drains away each step (leak), and when it crosses the line it tips over (fire) and empties. The "
            "fired spike is what goes to the next neuron, not the leaked charge.")
title(s, "LIF = Leak, Integrate, Fire", sub="The neuron model our chip uses, shown as a leaky bucket")
for i, n in enumerate([2, 3, 5, 6]):
    x, y = 0.75 + (i % 2) * 6.25, 1.6 + (i // 2) * 2.52
    picture(s, os.path.join(IMG, "neuron_step%d.png" % n), x, y, w=6.0,
            descr="LIF step %d" % n)

# ===================================================== 6 LIF behaviour
s = d.slide(section=S1, notes="In numbers: each step v loses a quarter then adds the input current; fire and reset at "
            "the threshold. Over 8 steps the number of spikes grows with the input strength: 0 for no/negative input, "
            "2 for weak, 4 for medium, 8 for strong. The spike count is the neuron's output.")
title(s, "How a LIF neuron behaves")
box(s, 0.6, 1.7, 6.0, 1.5, fill=WHITE, line=PURPLE, line_w=2,
    txt=[[("v ← v − v/4 + I", {"font": "Cambria", "size": 20})],
         [("if v ≥ θ:  spike, then v ← 0", {"font": "Cambria", "size": 18})]], size=18, align="c")
text(s, 0.6, 3.35, 6.0, 0.5, "leak (÷4) · integrate (+I) · fire & reset, repeated 8 times", 14, GREY, italic=True)
bar_chart(s, 0.5, 3.9, 6.3, 2.9, ["no input", "weak", "medium", "strong"], [0, 2, 4, 8],
          [GREY, BLUE, PURPLE, RED], horizontal=True, number_format='0', size=13, title_txt="spikes in 8 steps vs input strength")
card(s, 7.1, 1.7, 5.65, 5.1, "What this means", [
    [("No / negative input ", {"bold": True}), ("→ 0 spikes (stays quiet)", {})],
    [("Weak input ", {"bold": True}), ("→ fires slowly (2 of 8)", {})],
    [("Strong input ", {"bold": True}), ("→ fires every step (8 of 8)", {})],
    "",
    [("The spike count encodes strength.", {"bold": True})],
    "The 'leak' makes it forget old input, so it reacts to RECENT activity — useful for spotting bursts and floods.",
    "",
    "Hardware cost: 1 register + 2 adders + 1 comparator + 1 reset mux. No multiplier."], body_size=14)

# ===================================================== 7 hardware datapath
s = d.slide(section=S1, notes="This is the whole neuron as logic: the register holds the charge; a shift (free wiring) "
            "and a subtract do the leak; an adder adds the input current; a comparator checks the threshold; a mux "
            "resets to 0 on a spike. The green path writes the new charge back each clock. Sixteen of these run in "
            "parallel in our chip.")
title(s, "One LIF neuron in hardware (logic diagram)")
picture(s, "/tmp/neuron_lif_datapath.png", 0.6, 1.5, w=12.1,
        descr="LIF neuron datapath: register, shift, subtract, adder, comparator, reset mux, feedback")
text(s, 0.6, 6.5, 12.1, 0.4, "register (charge) → >>2 & subtract (leak) → + I (integrate) → compare (fire) → reset mux · green = write-back each clock",
     14, GREY, italic=True)

# ===================================================== 8 real RTL
s = d.slide(section=S1, notes="The real tool-drawn schematic from Quartus RTL Viewer: snn_core, which holds 16 hidden + "
            "2 output LIF neurons. The teal flip-flop out_mal~reg0 is the register that holds the final verdict bit.")
title(s, "The real hardware: snn_core in Quartus RTL Viewer")
picture(s, os.path.join(IMG, "rtlviewer_snn_core.png"), 0.6, 1.45, w=8.1,
        descr="Quartus RTL Viewer schematic of snn_core")
card(s, 8.95, 1.45, 3.8, 5.0, "What you see", [
    [("Left: ", {"bold": True}), ("in_spikes[63:0] and the weights (w1, w2, b2), thresholds, leak", {})],
    [("Right: ", {"bold": True}), ("out_cnt0/1 (spike counts), out_mal (verdict)", {})],
    [("out_mal~reg0: ", {"bold": True}), ("the single flip-flop holding the verdict", {})],
    "Inside: the IDLE/ACC/LIF/OUT state machine + 16+2 LIF neurons"], body_size=14)

# ===================================================== 9 vs other models
s = d.slide(section=S1, notes="LIF sits between the too-simple IF and the too-expensive Izhikevich. IF has no leak so it "
            "never forgets. ALIF adds an adaptive threshold (more memory, +1 register). TTFS fires once and encodes "
            "timing (Zhou & Li use temporal coding for intrusion detection). Izhikevich is biologically rich but needs "
            "a multiplier. We chose LIF: the standard balance, no multiplier, and it forgets old input.")
title(s, "LIF vs other neuron models")
table(s, 0.6, 1.6, 12.15, [2.5, 3.5, 3.0, 3.1], [
    ["model", "how it works", "hardware per neuron", "trade-off"],
    ["IF (integrate-and-fire)", "like LIF but no leak", "register, adder, compare", "cheapest; never forgets, noisy"],
    [[("LIF (ours)", {"bold": True, "color": "B5761A"})], "leak ¼ each step, fire, reset", "register, 2 adders, compare, mux", "good balance; standard choice"],
    ["Adaptive LIF (ALIF)", "threshold rises after a spike", "+1 register, +1 adder", "longer memory; for slow scans"],
    ["Time-to-first-spike", "fire once, timing = value", "LIF + a timer", "very low power [Zhou & Li, ICPR 2020]"],
    ["Izhikevich", "2 variables, quadratic (v²)", "MULTIPLIER + 2 registers", "biologically rich; several× larger"]],
    size=13.5, row_h=0.72)
text(s, 0.6, 6.4, 12.15, 0.4, "Diagrams of each on the next slide; the SNN-vs-CNN power question is studied by Plagwitz et al. [ACM TECS, 2023].", 13, GREY, italic=True)

# ===================================================== 10 model diagrams
s = d.slide(section=S1, notes="The hardware of three alternatives, side by side: IF is the simplest, LIF adds the leak, "
            "Izhikevich needs a multiplier (the red block), which is why it is far larger.")
title(s, "The models as logic: simplest → richest")
picture(s, "/tmp/neuron_if.png", 0.5, 1.6, w=6.1, descr="IF neuron")
picture(s, "/tmp/neuron_lif.png", 6.7, 1.6, w=6.1, descr="LIF neuron")
picture(s, "/tmp/neuron_izhikevich.png", 0.5, 3.9, w=7.4, descr="Izhikevich neuron with multiplier")
card(s, 8.2, 3.95, 4.55, 2.95, "Why LIF for us", [
    [("No multiplier ", {"bold": True, "color": GREEN}), ("(unlike Izhikevich)", {})],
    [("Has memory ", {"bold": True, "color": GREEN}), ("(unlike IF)", {})],
    "Small, fast, and the leak means it reacts to recent bursts — exactly what flood/scan detection needs.",
    "Trained offline so the int8 weights run bit-exactly on the chip [Neftci et al., IEEE SPM 2019]."], body_size=14)

# ===================================================== 11 what is an SNN
s = d.slide(notes="A spiking neural network is just many of these neurons wired in layers. Ours is tiny: 64 inputs, "
            "16 hidden LIF neurons, 2 output LIF neurons (benign / malicious). The winner is whichever output fired "
            "more over the 8 steps.")
title(s, "From one neuron to a network (SNN)", sub="Our network: 64 → 16 → 2")
for i in range(6):
    badge(s, 1.3, 1.9 + i * 0.62, "", fill=AMBER if i in (0, 2, 4) else LINE, d=0.4)
text(s, 0.7, 5.95, 2.3, 0.4, "64 inputs (spikes)", 14, GREY, align="c")
for i in range(5):
    badge(s, 4.6, 2.1 + i * 0.72, "", fill=PURPLE, d=0.5)
text(s, 3.9, 5.95, 2.1, 0.4, "16 hidden LIF", 14, GREY, align="c")
for i in range(6):
    for j in range(5):
        line(s, 1.68, 2.1 + i * 0.62, 4.6, 2.35 + j * 0.72, color="DCE6E9", width=0.6)
badge(s, 7.3, 2.9, "", fill=GREEN, d=0.72)
badge(s, 7.3, 4.6, "", fill=RED, d=0.72)
for j in range(5):
    line(s, 5.1, 2.35 + j * 0.72, 7.3, 3.26, color="DCE6E9", width=0.6)
    line(s, 5.1, 2.35 + j * 0.72, 7.3, 4.96, color="DCE6E9", width=0.6)
text(s, 8.2, 2.95, 2.0, 0.6, "benign", 17, GREEN, bold=True, anchor="m")
text(s, 8.2, 4.65, 2.0, 0.6, "malicious", 17, RED, bold=True, anchor="m")
card(s, 9.9, 1.75, 2.85, 5.0, "The decision", [
    "Each of the 18 neurons is a LIF neuron.",
    "Run 8 time steps.",
    [("Winner = the output neuron that fired more.", {"bold": True})],
    "Weights (int8) are loaded at run time."], body_size=14)

# ===================================================== 12 application
s = d.slide(notes="Our application: classify every network packet, from its header, as benign or malicious, inside the "
            "network card, before the OS sees it. Why an SNN fits: no multipliers, works only on active inputs, and its "
            "built-in memory catches floods.")
title(s, "Why an SNN fits our application", sub="A packet classifier inside the network card, at line rate")
reasons = [("No multipliers", "spikes make every weight an add; 0 DSP blocks used on FPGA → small, low power"),
           ("Event-driven", "only the ~13 of 64 'active' header features are processed per packet"),
           ("Memory over time", "the leak + a rate window catch SYN floods and scans that single packets hide"),
           ("Fast enough", "~28 clock cycles per packet — keeps up with 1 Gb/s"),
           ("Retrain, don't rebuild", "weights are loaded at run time; no new chip needed"),
           ("Neuromorphic path", "on-chip learning (STDP) possible later")]
for i, (h, b) in enumerate(reasons):
    x, y = 0.6 + (i % 3) * 4.1, 1.75 + (i // 3) * 2.5
    card(s, x, y, 3.9, 2.3, h, b, badge_label=str(i + 1), badge_fill=GREEN, body_size=14)

# ===================================================== 13 power & area
s = d.slide(notes="Our measured hardware cost. On open-source sky130 the classifier places and routes to 1.28 mm2 and "
            "125 mW at 100 MHz, with zero multipliers. On FPGA it is tiny: 6% of a Cyclone V, 0 DSP blocks. The "
            "Cadence 90nm (Genus) numbers are being finalised on the university server.")
title(s, "Our hardware cost (power & area)")
hl = [("1.28 mm²", "sky130 die, placed & routed", INK), ("125 mW", "at 100 MHz (sky130, typical)", PURPLE),
      ("0", "multipliers / DSP blocks", "B5761A"), ("6 %", "of a Cyclone V FPGA", GREEN),
      ("~28", "clock cycles per packet", BLUE), ("28 k", "flip-flops (mostly buffer+weights)", GREY)]
for i, (big, small, c) in enumerate(hl):
    x, y = 0.6 + (i % 3) * 4.1, 1.8 + (i // 3) * 2.4
    box(s, x, y, 3.9, 2.15, fill=PALE)
    text(s, x, y + 0.2, 3.9, 1.0, big, 38, c, bold=True, font=HEAD, align="c", anchor="m")
    text(s, x + 0.2, y + 1.25, 3.5, 0.8, small, 14, INK, align="c")
text(s, 0.6, 6.75, 12.15, 0.4, "sky130 synthesis: SNN core 0.39 mm². Cadence 90 nm (Genus) area/timing/power: being finalised on the uni server.", 13, GREY, italic=True)

# ===================================================== 14 comparison with literature
s = d.slide(notes="How our approach compares with the literature. Most SNN intrusion-detection work runs off the data "
            "path (software or a neuromorphic chip fed by software). Taurus puts ML in a switch but uses non-spiking "
            "models. Generic FPGA SNN accelerators target images. Our step: an SNN fused into the NIC datapath, "
            "no multipliers, at line rate.")
title(s, "Our approach vs the literature")
table(s, 0.6, 1.55, 12.15, [4.0, 2.2, 2.0, 3.8], [
    ["work", "platform", "multipliers", "vs ours"],
    ["Alom & Taha [IJCNN 2017]", "TrueNorth chip", "—", "SNN IDS 90.1%, but off the data path (software feeds it)"],
    ["Zhou & Li [ICPR 2020]", "software / sim", "—", "temporal-coded SNN IDS; no line-rate hardware"],
    ["Taurus [ASPLOS 2022]", "switch ASIC", "many", "per-packet ML in-switch, but non-spiking (DNN/SVM)"],
    ["Plagwitz et al. [ACM TECS 2023]", "FPGA", "SNN: none", "shows SNN area/power can beat CNN only if sparse"],
    ["FPGA SNN accel. [VTC 2024]", "FPGA", "none", "image benchmarks; not fused with a NIC"],
    [[("Ours", {"bold": True, "color": "B5761A"})], "ASIC/FPGA NIC", [("0", {"bold": True})], "SNN fused in the NIC datapath, line rate, 0 DSP"]],
    size=13, row_h=0.62)
text(s, 0.6, 6.45, 12.15, 0.4, "Energy-efficient neuromorphic design: Na & Kim [Electronics 2025]; algorithm–hardware co-design: Nature Mach. Intell. 2026.", 12.5, GREY, italic=True)

# ===================================================== 15 references
s = d.slide(dark=True, notes="References: four journal papers and four conference papers, plus the two datasets.")
text(s, 0.6, 0.5, 12, 0.9, "References", 34, WHITE, bold=True, font=HEAD)
text(s, 0.6, 1.5, 6, 0.4, "Journal papers", 18, AMBER, bold=True)
jr = ["Neftci, Mostafa, Zenke, “Surrogate Gradient Learning in SNNs,” IEEE Signal Processing Magazine, 2019.",
      "Plagwitz, Hannig, Teich, Keszöcze, “To Spike or Not to Spike? SNN vs CNN on FPGA,” ACM Trans. Embedded Computing Systems, 2023.",
      "Na, Kim, “An Energy-Efficient Neuromorphic Processor … for Edge AI,” Electronics (MDPI), 2025.",
      "“Algorithm–hardware co-design of neuromorphic networks with dual memory pathways,” Nature Machine Intelligence, 2026."]
for i, r in enumerate(jr):
    text(s, 0.6, 2.0 + i * 0.72, 12.1, 0.68, [[("[J%d] " % (i + 1), {"bold": True, "color": AMBER}), (r, {"color": "E8F0F2"})]], size=13.5)
text(s, 0.6, 5.0, 6, 0.4, "Conference papers", 18, GREEN, bold=True)
cf = ["Alom, Taha, “Network Intrusion Detection … on Neuromorphic Computing System,” IEEE IJCNN, 2017.",
      "Zhou, Li, “SNNs with Single-Spike Temporal-Coded Neurons for Network Intrusion Detection,” IEEE ICPR, 2020.",
      "Swamy et al., “Taurus: A Data Plane Architecture for Per-Packet ML,” ACM ASPLOS, 2022.",
      "“Efficient Hardware Acceleration of SNNs using FPGA,” IEEE VTC2024-Spring, 2024."]
for i, r in enumerate(cf):
    text(s, 0.6, 5.45 + i * 0.42, 12.1, 0.4, [[("[C%d] " % (i + 1), {"bold": True, "color": GREEN}), (r, {"color": "E8F0F2"})]], size=13)
text(s, 0.6, 7.2, 12.1, 0.3, "Datasets: Moustafa & Slay, UNSW-NB15 (MilCIS 2015); Sharafaldin et al., CIC-IDS2017 (ICISSP 2018).", 11.5, "8FA8AF")

d.save(OUT)
print("wrote", OUT, "with", d.n, "slides")
