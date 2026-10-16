#!/usr/bin/env python3
"""Build docs/SNN_Firewall_Explained.pptx (needs python-pptx):  python3 docs/slides/make_deck.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deck_lib import *  # noqa: E402,F401,F403

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
IMG = os.path.join(DOCS, "img")
OUT = os.path.join(DOCS, "SNN_Firewall_Explained.pptx")

d = Deck()
S1, S2, S3, S4, S5 = ("1  What is an SNN", "2  Our design", "3  Verification", "4  Area, power, performance",
                      "5  Alternatives and next steps")


def section(num, name, blurb, notes):
    s = d.slide(dark=True, notes=notes)
    badge(s, 0.6, 2.35, str(num), d=1.0, size=34)
    text(s, 1.9, 2.25, 10.5, 1.2, name, 40, WHITE, bold=True, font=HEAD, anchor="m")
    text(s, 1.9, 3.5, 10.0, 1.4, blurb, 18, "B9CBD0")
    return s


# =================================================================== 1 title
s = d.slide(dark=True, notes="A spiking neural network that sits inside the network card and throws away malicious "
            "packets before the operating system ever sees them. This deck explains it from zero.")
for i, (cx, cy) in enumerate([(10.2, 1.2), (11.3, 2.0), (10.6, 3.1), (11.8, 3.6), (10.0, 4.3)]):
    badge(s, cx, cy, "", fill=[AMBER, GREEN, AMBER, RED, AMBER][i], d=0.42 if i % 2 else 0.6)
for (a, b) in [((10.5, 1.5), (11.5, 2.2)), ((11.5, 2.2), (10.9, 3.4)), ((10.9, 3.4), (12.0, 3.8)), ((10.9, 3.4), (10.3, 4.6))]:
    line(s, a[0], a[1], b[0], b[1], color="3E6A75", width=2)
text(s, 0.6, 1.3, 9.2, 2.2, "A spiking neural network\nthat guards the network card", 38, WHITE, bold=True, font=HEAD)
text(s, 0.6, 3.75, 8.6, 1.2, "SNN packet firewall: what it is, how the hardware works, how we tested it, "
     "and what it costs in area, power and speed", 20, "B9CBD0")
text(s, 0.6, 6.2, 9, 0.4, "SNN_based_network_packet_classifier · explained simply", 14, "8FA8AF")

# =================================================================== 2 roadmap
s = d.slide(notes="Five parts. Each starts from zero, so skip what you already know.")
title(s, "What this deck covers")
parts = [("1", "What is an SNN", "Neurons, spikes, and how SNNs differ from normal and convolutional networks", AMBER),
         ("2", "Our design", "From an Ethernet frame to 64 spikes to a verdict, and the HDL behind each neuron", GREEN),
         ("3", "Verification", "The testbench, the test vectors, the functional verification table, the xrun signals", BLUE),
         ("4", "Area, power, performance", "Measured numbers on sky130, FPGAs; SNN vs other approaches", PURPLE),
         ("5", "Alternatives", "Other neuron models and other ways to build the whole project", RED)]
for i, (n, h, b, c) in enumerate(parts):
    x = 0.6 + i * 2.48
    box(s, x, 1.7, 2.3, 4.6, fill=PALE)
    badge(s, x + 0.2, 1.9, n, fill=c, color=WHITE if c != AMBER else INK, d=0.65, size=22)
    text(s, x + 0.2, 2.75, 1.95, 0.95, h, 19, INK, bold=True, font=HEAD)
    text(s, x + 0.2, 3.75, 1.95, 2.4, b, 15, INK)

# =================================================================== 3 problem
s = d.slide(section="Introduction", notes="Today the operating system receives every packet and only then software "
            "inspects it. We move the inspection into the network card hardware.")
title(s, "The problem and the idea")
box(s, 0.6, 1.6, 5.9, 4.9, fill=PALE)
text(s, 0.9, 1.8, 5.4, 0.5, "Today", 22, RED, bold=True, font=HEAD)
for i, t in enumerate(["Network", "Network card", "Operating system", "Firewall / IDS software"]):
    box(s, 1.2, 2.5 + i * 0.95, 4.7, 0.65, fill=WHITE, line=LINE, txt=t, size=16)
    if i < 3:
        arrow(s, 3.55, 3.15 + i * 0.95, 3.55, 3.45 + i * 0.95)
text(s, 0.9, 6.25, 5.5, 0.4, "the attack is already inside the OS when it is checked", 14, RED, italic=True)
box(s, 6.85, 1.6, 5.9, 4.9, fill=PALE)
text(s, 7.15, 1.8, 5.4, 0.5, "Our design", 22, GREEN, bold=True, font=HEAD)
box(s, 7.45, 2.5, 4.7, 0.65, fill=WHITE, line=LINE, txt="Network", size=16)
arrow(s, 9.8, 3.15, 9.8, 3.45)
box(s, 7.45, 3.45, 4.7, 1.55, fill=WHITE, line=GREEN, line_w=2.5,
    txt=[[("Network card + SNN guard", {"bold": True})], "judges every frame in ~28 clock ticks", "erases malicious frames"], size=16)
arrow(s, 9.8, 5.0, 9.8, 5.3)
box(s, 7.45, 5.3, 4.7, 0.65, fill=WHITE, line=LINE, txt="Operating system: only benign frames", size=16)
text(s, 7.15, 6.25, 5.5, 0.4, "malicious frames never reach the OS", 14, GREEN, italic=True)

# =================================================================== PART 1
section(1, "What is a spiking neural network?",
        "Neurons, spikes, leaks and thresholds, and how an SNN differs from the neural networks you already know.",
        "Part 1 builds the vocabulary: neuron, weight, threshold, spike, time step.")

# ---- 5 neuron
s = d.slide(section=S1, notes="A neuron is a tiny calculator: it adds up its inputs, each multiplied by a weight, and "
            "decides whether to pass something on. Weights are what training learns.")
title(s, "What is a neuron?", sub="The building block of every neural network")
ins = [("is it TCP?", "1", "+12"), ("SYN flag set?", "1", "+40"), ("port 0?", "0", "+90")]
for i, (q, v, w) in enumerate(ins):
    y = 2.0 + i * 1.35
    box(s, 0.6, y, 2.6, 0.8, fill=PALE, txt=q, size=15)
    badge(s, 3.4, y + 0.12, v, fill=AMBER if v == "1" else LINE, d=0.56, size=16)
    arrow(s, 3.96, y + 0.4, 6.05, 3.35 + (i - 1) * 0.35, color=GREY, width=1.75)
    text(s, 4.1, y - 0.22 if i < 2 else y + 0.62, 1.4, 0.35, "weight " + w, 13, GREY)
box(s, 6.1, 2.5, 1.9, 1.9, fill=PURPLE, shape="oval", txt=[[("Σ", {"size": 30, "bold": True})], "add up"], color=WHITE, size=15)
arrow(s, 8.0, 3.45, 8.9, 3.45)
box(s, 8.9, 2.9, 1.7, 1.1, fill=WHITE, line=PURPLE, line_w=2, txt="over the\nthreshold?", size=15)
arrow(s, 10.6, 3.45, 11.3, 3.45)
box(s, 11.3, 2.9, 1.5, 1.1, fill=AMBER, txt=[[("fire", {"bold": True})], "(output 1)"], size=15)
bullets(s, 0.6, 6.0, 12.2, 0.9, [[("Inputs × weights, summed, compared with a threshold. ", {"bold": True}),
        ("The weights are the only thing training learns: positive weights push towards firing, negative weights hold it back.", {})]],
        size=15)

# ---- 6 normal vs spiking neuron
s = d.slide(section=S1, notes="A normal artificial neuron outputs a number once. A spiking neuron keeps a charge over "
            "several time steps and outputs short yes/no pulses called spikes.")
title(s, "Normal neuron vs spiking neuron")
for col, (hd, c, lines_, formula) in enumerate([
        ("Normal (ANN / CNN) neuron", BLUE,
         ["Computes once per input", "Output is a number (e.g. 0.73)", "Needs multiplications (input × weight)", "No memory between inputs"],
         "y = f( Σ wᵢ·xᵢ + b )"),
        ("Spiking (SNN) neuron: ours", AMBER,
         ["Runs for several time steps (we use 8)", "Output is a spike: 1 or 0 at each step", "Inputs are spikes, so input × weight = add or skip",
          "Keeps a charge (membrane) between steps"],
         "v ← v − v/4 + I   ·   spike if v ≥ θ, then v ← 0")]):
    x = 0.6 + col * 6.25
    box(s, x, 1.6, 5.9, 4.95, fill=PALE)
    text(s, x + 0.3, 1.8, 5.4, 0.5, hd, 21, c if c != AMBER else "B5761A", bold=True, font=HEAD)
    box(s, x + 0.3, 2.45, 5.3, 0.8, fill=WHITE, line=c, line_w=2, txt=formula, size=18, font="Cambria")
    bullets(s, x + 0.3, 3.5, 5.4, 2.9, lines_, size=16)

# ---- 7 LIF over time
v, I, th, vs, spikes = 0, 100, 256, [], []
for t in range(8):
    v = v - (v >> 2) + I
    vs.append(v)
    spikes.append(v >= th)
    if v >= th:
        v = 0
s = d.slide(section=S1, notes="A leaky bucket: water (input current) pours in every step, a quarter leaks out, and "
            "when the level passes the line the bucket tips: that is a spike, and it starts empty again. "
            "Numbers are the real arithmetic of our hidden neurons (leak 1/4, threshold 256) with input current 100.")
title(s, "A spiking neuron over time: the leaky bucket", sub="Leaky integrate-and-fire (LIF), the neuron model our hardware uses")
line_chart(s, 0.6, 1.75, 7.6, 4.9, ["t%d" % (i + 1) for i in range(8)],
           [("membrane charge v (before firing)", vs), ("threshold θ = 256", [th] * 8)], [PURPLE, RED])
card(s, 8.6, 1.75, 4.15, 4.9, "Each time step", [
    [("1  leak: ", {"bold": True}), ("lose a quarter of the charge", {})],
    [("2  integrate: ", {"bold": True}), ("add the input current I (here 100)", {})],
    [("3  fire: ", {"bold": True}), ("if v ≥ 256, send a spike and reset to 0", {})],
    "",
    [("Result here: spikes at t%s and t%s." % tuple(str(i + 1) for i, sp in enumerate(spikes) if sp), {"bold": True, "color": "B5761A"})],
    "A stronger input fires more often; the number of spikes carries the information."], body_size=15)

# ---- 8 software view
s = d.slide(section=S1, notes="In software all three are trained the same broad way (gradient descent), but SNNs need a "
            "trick because a spike has no slope: surrogate gradients.")
title(s, "ANN vs CNN vs SNN in software")
table(s, 0.6, 1.6, 12.15, [2.2, 3.3, 3.3, 3.4], [
    ["", "MLP / ANN", "CNN", "SNN (ours)"],
    ["Data inside", "numbers (floats or int8)", "numbers, on 2-D/1-D grids (images, byte sequences)", "spikes: 0/1 per time step"],
    ["Basic operation", "multiply-accumulate", "sliding filters = many multiply-accumulates", "add the weight if a spike arrived, leak, compare"],
    ["Time", "one pass", "one pass", "T steps (we use 8); neurons keep state"],
    ["Training", "back-propagation", "back-propagation", "back-propagation with surrogate gradients (spikes have no slope)"],
    ["Typical tools", "PyTorch / TensorFlow", "PyTorch / TensorFlow", "PyTorch + custom integer model (model/train.py, snn_int.py)"],
    ["Good at", "tabular features", "images, raw byte patterns", "sparse, event-like inputs; low-power hardware"]],
    size=14, row_h=0.62)

# ---- 9 hardware view
s = d.slide(section=S1, notes="The hardware difference is what matters for us: a CNN accelerator is an array of "
            "multipliers fed by big buffers; our SNN is a handful of adders, an event queue and some state registers.")
title(s, "CNN vs SNN in hardware")
for col, (hd, c, blocks, foot) in enumerate([
        ("CNN accelerator", BLUE, ["large weight and activation buffers (10–100 KB)", "array of multipliers (MAC units / DSP blocks)",
                                   "line buffers to slide the filters", "~10⁵–10⁶ multiply-accumulates per input"],
         "fast on dense data, but multipliers and big buffers cost area and power"),
        ("Our SNN", AMBER, ["small weight memory (1.1 KB, int8)", "16 adders + 2-stage adder tree, no multipliers",
                            "event queue: only the 'yes' inputs are visited", "~900 additions/compares per frame"],
         "0 DSP blocks used on both FPGAs; extra state: one 20-bit charge per neuron")]):
    x = 0.6 + col * 6.25
    text(s, x, 1.55, 5.9, 0.5, hd, 22, c if c != AMBER else "B5761A", bold=True, font=HEAD)
    for i, b in enumerate(blocks):
        box(s, x, 2.15 + i * 0.95, 5.9, 0.78, fill=PALE, txt=b, size=16, align="l")
    text(s, x, 6.05, 5.9, 0.7, foot, 15, GREY, italic=True)

# ---- 10 pros
s = d.slide(section=S1, notes="Why an SNN fits a network card: binary inputs make the arithmetic trivial, most inputs are "
            "zero, flood detection needs memory over time, and on-chip learning is possible later.")
title(s, "Why an SNN suits this project")
pros = [("No multipliers", "Inputs are 1-bit spikes, so every weight is either added or skipped. 0 DSP blocks on both FPGAs."),
        ("Work only on activity", "On average only 13.5 of the 64 inputs are 'yes' (79 % zeros). Only those weight rows are read."),
        ("Built-in memory over time", "Neurons keep their charge; together with the SYN/ping rate window this catches floods per packet."),
        ("Fast enough for 1 Gb/s", "~28 clock ticks per decision vs 84 byte-times for the smallest frame: 3× headroom."),
        ("Weights load at run time", "Retrain in Python, write 276 registers. No new chip or bitstream."),
        ("Path to on-chip learning", "STDP (from the original snn_stdp design) could adapt the weights in the field later.")]
for i, (h, b) in enumerate(pros):
    x, y = 0.6 + (i % 3) * 4.1, 1.6 + (i // 3) * 2.55
    card(s, x, y, 3.9, 2.35, h, b, badge_label=str(i + 1), badge_fill=GREEN, body_size=15)

# ---- 11 cons
s = d.slide(section=S1, notes="Be honest about the costs: latency of several time steps, extra state, harder training, and "
            "the energy advantage is not automatic. Accuracy on real traffic is still to be measured.")
title(s, "Limits and costs, honestly")
cons = [("Several time steps", "8 iterations instead of one pass. Fine here (28 ≪ 84 ticks), but a one-pass network would be faster."),
        ("Extra state", "Each neuron needs a 20-bit charge register: ~990 flip-flops in our network. A plain MLP needs none."),
        ("Harder training", "Spikes are not differentiable: surrogate gradients and integer-exact simulation are needed."),
        ("No automatic energy win", "Plagwitz et al. 2023: on FPGAs SNNs can lose to CNNs in power on small tasks unless sparsity and clock gating are exploited."),
        ("Accuracy unproven on real traffic", "99.7 % so far is on synthetic traffic. Real datasets (UNSW-NB15, CIC-IDS2017) come next."),
        ("Memory dominates", "Our chip is 74 % flip-flops, mostly the packet buffer and weights, not the neurons. SRAM would fix it.")]
for i, (h, b) in enumerate(cons):
    x, y = 0.6 + (i % 3) * 4.1, 1.6 + (i // 3) * 2.55
    card(s, x, y, 3.9, 2.35, h, b, badge_label=str(i + 1), badge_fill=RED, body_size=15)

# =================================================================== PART 2
section(2, "Our design", "From an Ethernet frame to 64 yes/no spikes to a verdict, and the hardware inside each neuron.",
        "Part 2 follows one frame through the chip.")

# ---- 13 architecture image
s = d.slide(section=S2, notes="Frames wait in the buffer while the header is turned into 64 yes/no answers and the SNN "
            "judges them. Benign frames are released, malicious ones erased. The same block runs on three targets.")
title(s, "The architecture in one picture")
picture(s, os.path.join(IMG, "architecture_simple.png"), 1.25, 1.35, w=10.8,
        descr="Network to MAC to the firewall block (packet buffer, header reader, 64 questions, spiking neural net, verdict gate) to the computer")
text(s, 1.25, 6.45, 10.8, 0.4, "Never blocks the network · keeps frame order · drops whole frames only when overloaded", 15, GREY, italic=True)

# ---- 14 frame to spikes
s = d.slide(section=S2, notes="The header is turned into 64 yes/no answers. Frame 0 of the test vectors is an ordinary ping: "
            "9 answers are yes.")
title(s, "From a frame to 64 yes/no spikes", sub="pkt_parser reads the header; spike_encoder asks 64 questions")
table(s, 0.6, 1.85, 6.6, [1.0, 4.2, 1.4], [
    ["bits", "question", "type"],
    ["1–8", "IPv4? ARP? IPv6? TCP? UDP? ICMP?", "protocol"],
    ["15–23", "TTL bucket? IP length bucket?", "size"],
    ["24–26", "source = destination? bogus source? broadcast?", "suspicious"],
    ["27–33", "TCP flags FIN SYN RST PSH ACK URG, none set?", "flags"],
    ["34–41", "port 0? well-known? registered? high?", "ports"],
    ["57–60", "≥ 8 / ≥ 16 SYNs or pings in the last 32 frames?", "rate (memory)"],
    ["62–63", "SSH / Telnet / SMB / RDP port? DNS?", "services"]], size=14, row_h=0.56)
card(s, 7.6, 1.85, 5.15, 4.75, "Example: frame 0, a ping", [
    "Bytes: 02 98 ca d7 … 08 00 45 00 00 54 … 40 01 …",
    [("Spikes: 0x0022000000111283", {"bold": True})],
    "Yes to 9 questions:",
    "bias · IPv4 · ICMP · header length 5 · don't-fragment · TTL 9–64 · length 41–100 · echo request · payload 9–64",
    [("SNN: benign neuron 4 spikes, malicious 0 → benign", {"bold": True, "color": GREEN})]], body_size=15)

# ---- 15 network
s = d.slide(section=S2, notes="64 inputs feed 16 hidden neurons, which feed two output neurons. Whichever output fires "
            "more in 8 steps wins.")
title(s, "Our network: 64 → 16 → 2")
for i in range(8):
    badge(s, 1.0, 1.75 + i * 0.6, "", fill=AMBER if i in (0, 1, 3, 6) else LINE, d=0.38)
text(s, 0.4, 6.6, 2.2, 0.4, "64 input spikes", 14, GREY, align="c")
for i in range(6):
    badge(s, 4.2, 1.9 + i * 0.78, "", fill=PURPLE, d=0.5)
text(s, 3.5, 6.6, 2.0, 0.4, "16 hidden LIF", 14, GREY, align="c")
for i in range(8):
    for j in range(6):
        line(s, 1.38, 1.94 + i * 0.6, 4.2, 2.15 + j * 0.78, color="D7E2E5", width=0.75)
badge(s, 7.0, 2.6, "", fill=GREEN, d=0.7)
badge(s, 7.0, 4.2, "", fill=RED, d=0.7)
for j in range(6):
    for k, yy in enumerate((2.95, 4.55)):
        line(s, 4.7, 2.15 + j * 0.78, 7.0, yy, color="D7E2E5", width=0.75)
text(s, 7.85, 2.65, 1.8, 0.6, "benign", 16, GREEN, bold=True, anchor="m")
text(s, 7.85, 4.25, 1.8, 0.6, "malicious", 16, RED, bold=True, anchor="m")
card(s, 9.6, 1.6, 3.15, 5.0, "Rules", [
    "W1: 64×16 int8 weights", "W2: 16×2 int8 weights", "Thresholds 256 / 128", "Leak: lose 1/4 per step", "8 time steps",
    [("Decision: ", {"bold": True}), ("malicious if its neuron fired more often (tie: higher charge)", {})]], body_size=14)

# ---- 16 HDL architecture
s = d.slide(section=S2, notes="snn_core.v. The input current is computed once per frame by visiting only the yes-inputs, "
            "one weight row per clock. Then 8 LIF steps run with all 16 hidden neurons in parallel, and the output layer "
            "follows two cycles behind through a pipelined adder tree.")
title(s, "HDL architecture of the neurons (snn_core.v)")
stages = [("pend[63:0]\n+ lowest-'1' finder", "which input next?", TEAL),
          ("W1 memory\n4 banks × 64 × 32 bit", "one row = 16 weights", BLUE),
          ("16 accumulators\nacc[h] += W1[row][h]", "input current, once", PURPLE),
          ("16 LIF neurons\nv − v>>2 + acc ≥ TH1", "8 steps, in parallel", PURPLE),
          ("adder tree, 2 pipeline\nstages: Σ W2 · spikes", "output current", BLUE),
          ("2 output LIF + spike\ncounters cnt0 / cnt1", "≥ TH2 → count", RED)]
for i, (b, cap, c) in enumerate(stages):
    x = 0.6 + i * 2.07
    box(s, x, 1.75, 1.85, 1.5, fill=c, txt=b, size=13, color=WHITE, bold=True)
    text(s, x, 3.3, 1.85, 0.4, cap, 13, GREY, align="c")
    if i < 5:
        arrow(s, x + 1.85, 2.5, x + 2.07, 2.5)
text(s, 0.6, 3.95, 4.0, 0.45, "Control: a 4-state machine", 18, INK, bold=True, font=HEAD)
for i, (st, ex) in enumerate([("IDLE", "wait for a spike vector"), ("ACC", "1 clock per 'yes' input"),
                              ("LIF", "8 time steps"), ("OUT", "decide, report")]):
    x = 0.6 + i * 3.05
    box(s, x, 4.5, 2.6, 0.75, fill=AMBER if st != "IDLE" else PALE, shape="round", txt=st, size=17, bold=True)
    text(s, x, 5.3, 2.6, 0.4, ex, 14, GREY, align="c")
    if i < 3:
        arrow(s, x + 2.6, 4.87, x + 3.05, 4.87)
box(s, 0.6, 5.95, 12.15, 0.75, fill=PALE, txt=[[("Latency per frame = (number of 'yes' inputs) + 8 + 6 cycles ≈ 28 cycles.   ", {"bold": True}),
                                                ("No multipliers: every product is 'add the weight or not'.", {})]], size=15, align="l")

# ---- 17 one LIF neuron in hardware
s = d.slide(section=S2, notes="One hidden neuron in gates: a 20-bit register, a shift that is just wiring, two adders, a "
            "comparator and a reset multiplexer. Sixteen copies run side by side.")
title(s, "One LIF neuron in hardware", sub="v ← v − (v >>> 2) + I ;  spike = (v ≥ TH1) ;  if spike: v ← 0")
blocks = [(0.7, 3.0, 1.8, 1.1, "v register\n20 bit", PURPLE, WHITE),
          (3.1, 1.9, 1.8, 1.0, ">>> 2\n(just wiring)", PALE, INK),
          (3.1, 3.05, 1.8, 1.0, "subtract\nv − v/4", BLUE, WHITE),
          (5.5, 3.05, 1.8, 1.0, "add\n+ I (acc)", BLUE, WHITE),
          (7.9, 3.05, 1.8, 1.0, "compare\n≥ TH1", AMBER, INK),
          (7.9, 4.6, 1.8, 1.0, "mux\nspike ? 0 : v", PALE, INK),
          (10.4, 3.05, 1.8, 1.0, "spike\n(1 bit, registered)", RED, WHITE)]
for x, y, w_, h_, t, f, c in blocks:
    box(s, x, y, w_, h_, fill=f, txt=t, size=14, color=c, bold=True, line=LINE if f == PALE else None)
arrow(s, 2.5, 3.4, 3.1, 2.4)
arrow(s, 2.5, 3.55, 3.1, 3.55)
arrow(s, 4.0, 2.9, 4.0, 3.05)
arrow(s, 4.9, 3.55, 5.5, 3.55)
arrow(s, 7.3, 3.55, 7.9, 3.55)
arrow(s, 9.7, 3.55, 10.4, 3.55)
arrow(s, 8.8, 4.05, 8.8, 4.6)
arrow(s, 7.9, 5.1, 1.6, 5.1, color=GREY)
arrow(s, 1.6, 5.1, 1.6, 4.1, color=GREY)
text(s, 2.4, 5.15, 5.0, 0.4, "new charge, written back every time step", 13, GREY)
box(s, 0.6, 5.85, 12.15, 0.8, fill=PALE, align="l", size=15, txt=[[("Cost of one neuron:  ", {"bold": True}),
    ("one 20-bit register + 2 adders + 1 comparator + 1 multiplexer · no multiplier · 16 copies run in parallel", {})]])

# ---- 18 life of a frame
s = d.slide(section=S2, notes="A frame takes as many clock ticks to arrive as it has bytes. The verdict is ready about 30 "
            "ticks after the last byte, then the stored frame is released or skipped.")
title(s, "Life of one frame, clock by clock")
steps = [("0 … L−1", "bytes arrive, 1 per clock; stored and read at the same time"),
         ("L", "last byte: keep the frame (commit) or roll it back (bad checksum, no room)"),
         ("L+1", "header fields ready (pkt_parser)"), ("L+2", "64 spikes ready (spike_encoder)"),
         ("+ ~28", "SNN verdict (snn_core)"), ("then", "benign: stream the stored bytes out · malicious: skip them")]
for i, (t, d_) in enumerate(steps):
    y = 1.45 + i * 0.8
    box(s, 0.6, y, 1.9, 0.68, fill=AMBER if i == 4 else PALE, txt=t, size=16, bold=True)
    text(s, 2.75, y, 10.0, 0.68, d_, 17, INK, anchor="m")
text(s, 0.6, 6.4, 12, 0.4, "Smallest frame on the wire = 84 byte-times; a decision needs ~28: the classifier keeps up with 1 Gb/s.", 15, GREY, italic=True)

# =================================================================== PART 3
section(3, "Verification", "What a testbench is, what the test vectors are, what each test proves, and what all those xrun signals mean.",
        "Part 3 explains the simulation you ran with xrun.")

# ---- 20 testbench
s = d.slide(section=S3, notes="The testbench is a program around the design. It pretends to be the network, the computer "
            "and the CPU, and compares everything with the answers the Python model computed in advance.")
title(s, "What is a testbench?", sub="sim/asic/tb_snn_asic.sv: a simulated world around the design")
box(s, 4.6, 2.9, 4.1, 1.7, fill=TEAL, txt=[[("design under test", {"size": 14})], [("snn_pkt_filter_asic", {"bold": True, "size": 18})]], color=WHITE)
roles = [(0.6, 1.8, "plays the NETWORK", "sends 600 frames byte by byte (s_axis_*)", BLUE),
         (0.6, 4.3, "plays the CPU", "loads weights, sets modes, reads counters (cfg_*)", PURPLE),
         (9.4, 1.8, "plays the COMPUTER", "receives frames, sometimes busy (m_axis_*)", GREEN),
         (9.4, 4.3, "CHECKS everything", "verdicts, every byte, counters vs golden model", RED)]
for x, y, h_, b, c in roles:
    box(s, x, y, 3.35, 1.7, fill=PALE)
    text(s, x + 0.2, y + 0.15, 3.0, 0.5, h_, 17, c, bold=True)
    text(s, x + 0.2, y + 0.7, 3.0, 0.95, b, 15, INK)
arrow(s, 3.95, 2.65, 4.6, 3.3)
arrow(s, 3.95, 5.15, 4.6, 4.3)
arrow(s, 8.7, 3.3, 9.4, 2.65)
arrow(s, 8.7, 4.3, 9.4, 5.15, dash=True)
box(s, 0.6, 6.25, 12.15, 0.6, fill=PALE, txt="Any difference prints [ERR] …; every test ends PASS or FAIL; the run ends with RESULT: PASS (10 tests)", size=15)

# ---- 21 vectors
s = d.slide(section=S3, notes="Test vectors are just three text files: the inputs, the trained weights, and the answer sheet. "
            "Python writes them; every simulation and the board test read them.")
title(s, "The test vectors: three files", sub="written by model/export.py into sim/vectors/")
for i, (f, h_, b, c) in enumerate([
        ("frames.txt", "600 network frames", "one frame per line as hex bytes, in time order, like a recording of real traffic", BLUE),
        ("cfg.txt", "the trained brain", "276 register writes: thresholds, time steps, leak, output biases, all weights", PURPLE),
        ("expected.txt", "the answer sheet", "per frame: the 64 spikes, spikes of each output neuron, verdict, true label, attack kind", GREEN)]):
    x = 0.6 + i * 4.1
    box(s, x, 1.9, 3.9, 3.0, fill=PALE)
    box(s, x + 0.25, 2.1, 3.4, 0.6, fill=c, txt=f, size=17, color=WHITE, bold=True, font="Courier New")
    text(s, x + 0.25, 2.85, 3.4, 0.5, h_, 18, INK, bold=True)
    text(s, x + 0.25, 3.4, 3.4, 1.4, b, 15, INK)
box(s, 0.6, 5.25, 12.15, 1.45, fill=WHITE, line=LINE, align="l", size=15, txt=[
    [("expected.txt line 1:  ", {"bold": True}), ("0022000000111283   4   0   0   0   benign", {"font": "Courier New"})],
    "spikes (hex)  ·  benign-neuron spikes  ·  malicious-neuron spikes  ·  verdict (0 = benign)  ·  true label  ·  kind"])

# ---- 22 story
s = d.slide(section=S3, notes="The 600 frames tell a story: a normal day, a SYN flood, port-0 probes, an ACK scan, normal again.")
title(s, "The story told by the 600 frames")
segs = [(0, 46, "normal", GREEN), (47, 247, "SYN flood", RED), (248, 259, "", GREEN), (260, 276, "", AMBER),
        (277, 340, "normal", GREEN), (341, 589, "ACK scan (mixed)", PURPLE), (590, 599, "", GREEN)]
x0, wtot = 0.6, 12.15
for a, b, lab, c in segs:
    x = x0 + wtot * a / 600
    w_ = wtot * (b - a + 1) / 600
    box(s, x, 1.9, w_, 0.85, fill=c, shape="rect", txt=lab, size=14, color=WHITE if c != AMBER else INK, bold=True)
text(s, x0 + wtot * 268 / 600 - 0.6, 1.5, 1.2, 0.35, "port 0 ↓", 13, "B5761A", bold=True, align="c")
for f in (0, 100, 200, 300, 400, 500, 600):
    text(s, x0 + wtot * f / 600 - 0.4, 2.8, 0.8, 0.3, str(f), 12, GREY, align="c")
attacks = [("SYN flood (153 frames)", "fake 'let's connect' requests to exhaust a server. One SYN looks normal; many in a row turn on the rate questions.", RED),
           ("ACK scan (41 frames)", "ACK packets that belong to no connection, used to map which ports a firewall filters.", PURPLE),
           ("Port 0 (4 frames)", "traffic to port 0, which no real service uses: probing or fingerprinting.", AMBER)]
for i, (h_, b, c) in enumerate(attacks):
    x = 0.6 + i * 4.1
    card(s, x, 3.45, 3.9, 2.55, h_, b, head_color=c if c != AMBER else "B5761A", body_size=15)
text(s, 0.6, 6.2, 12.15, 0.6, "402 benign + 198 malicious. The design flags 197, with 0 false alarms; the one miss (frame 128) is missed by the Python model too.",
     15, INK)

# ---- 23 composition chart
s = d.slide(section=S3, notes="What kinds of frames are inside. Mostly normal TCP acknowledgements and data.")
title(s, "What is inside the 600 frames")
bar_chart(s, 0.6, 1.5, 12.15, 5.3,
          ["TCP ACK (normal)", "TCP data / PSH (normal)", "TCP FIN (normal)", "TCP SYN (normal)", "other TCP (normal)",
           "ping and reply (normal)", "DNS (normal)", "other (ARP, IPv6, UDP, fragments)", "SYN flood (attack)", "ACK scan (attack)", "port 0 (attack)"],
          [193, 90, 30, 23, 23, 21, 12, 10, 153, 41, 4], [GREEN] * 8 + [RED, PURPLE, AMBER], horizontal=True, size=13)

# ---- 24-26 FV table
FV = [("T1", "Reset", "reset, read every register", "safe start: blocking on, defaults, counters 0, never stalls the MAC", "cfg_rdata, s_axis_tready = 1"),
      ("T2", "Load the brain", "write 276 weights, read back", "registers hold what was written", "cfg_wr, cfg_addr, cfg_rdata"),
      ("T3", "Normal operation", "all 600 frames, gaps 12–40, host 90 % ready", "every verdict = Python model; only benign frames out, byte-exact", "s_axis_*, m_axis_*, verdict_*"),
      ("T4", "Monitor mode", "CTRL = 0, frames 0–149", "still judges and counts, forwards all 150", "verdict_mal pulses but m_axis shows all frames"),
      ("T5", "Bypass", "CTRL.bypass = 1", "forwards everything (off switch)", "same as T4"),
      ("T6", "Corrupted frames", "every 5th frame marked bad (tuser)", "erased whole, no verdict, counted", "s_axis_tuser pulses (only here)"),
      ("T7", "Size limits", "2148 B, 8 B, 1518 B frames", "too-big dropped whole; tiny and max-size pass intact", "one very long input frame, no output for it"),
      ("T8", "Full speed", "250 frames, 20 idle cycles apart", "keeps up with 1 Gb/s: 0 drops, bit-exact", "regular frames, m_axis_tready flat"),
      ("T9", "Overload", "gaps 1–3, host only 35 % ready", "drops whole frames, none corrupted or reordered", "input dense, output throttled"),
      ("T10", "Reset mid-traffic", "reset during a half frame, then 60 frames", "clean restart, then perfect again", "rst pulse, counters read 0, weights reloaded")]
for part, (lo, hi) in enumerate([(0, 4), (4, 7), (7, 10)]):
    s = d.slide(section=S3, notes="Functional verification table, part %d of 3. Each test is a real-world situation; the "
                "right-hand column says what it looks like in the xrun waveform." % (part + 1))
    title(s, "Functional verification table (%d/3)" % (part + 1), sub="10 tests, all PASS in xrun (RTL), Questa (RTL) and on the gate-level netlist")
    rows = [["test", "situation", "what the testbench does", "expected behaviour (PASS)", "what you see in the waveform"]]
    rows += [[a, b, c, e, f] for a, b, c, e, f in FV[lo:hi]]
    table(s, 0.6, 1.8, 12.15, [0.7, 1.7, 3.0, 3.6, 3.15], rows, size=14, row_h=1.0 if hi - lo == 3 else 0.9)

# ---- 27 waveform
s = d.slide(section=S3, notes="Your xrun run. Read it left to right: the config writes mark the boundaries between tests.")
title(s, "Reading your xrun waveform")
picture(s, os.path.join(IMG, "xrun_rtl_waveform.png"), 0.6, 1.4, w=8.0,
        descr="SimVision waveform of the passing xrun run, 3.2 ms, all top-level ports")
tl = [("0 – 1.03 ms", "T1–T3: weights, 600 golden frames"), ("≈ 1.03 ms", "T4: CTRL = 0 (monitor)"), ("≈ 1.27 ms", "T5: CTRL = 3 (bypass)"),
      ("1.51 – 1.69", "T6: the only s_axis_tuser pulses"), ("≈ 1.7 – 1.8", "T7: one 2148-byte frame"), ("1.8 – 2.09", "T8: full speed, tready flat"),
      ("2.09 – 3.1", "T9: overload"), ("3.13 – 3.2", "T10: reset, counters 0, reload")]
for i, (t, e) in enumerate(tl):
    y = 1.45 + i * 0.66
    box(s, 8.85, y, 1.6, 0.56, fill=AMBER if i in (3, 6) else PALE, txt=t, size=13, bold=True)
    text(s, 10.55, y, 2.25, 0.56, e, 13, INK, anchor="m")
text(s, 0.6, 6.05, 8.0, 0.8, "Ends at 3,200,784 ns: the testbench reached $finish with RESULT: PASS (10 tests).", 15, GREY, italic=True)

# ---- 28 signal glossary
s = d.slide(section=S3, notes="Every signal in the waveform, grouped. s_ is input from the network, m_ is output to the computer.")
title(s, "What every xrun signal means")
table(s, 0.6, 1.5, 12.15, [2.4, 3.3, 6.45], [
    ["group", "signals", "meaning"],
    ["clock / reset", "clk, rst", "125 MHz clock (8 ns, 1 GbE byte clock); synchronous reset"],
    ["frames IN (from network)", "s_axis_tdata[7:0], tvalid, tlast", "one byte per clock while tvalid = 1; tlast marks the last byte of a frame"],
    ["", "s_axis_tuser", "'this frame is damaged' (bad checksum): only in T6"],
    ["", "s_axis_tready", "always 1: the firewall never asks the network to wait"],
    ["frames OUT (to computer)", "m_axis_tdata[7:0], tvalid, tlast", "only benign (or, in monitor/bypass, all) frames, byte-exact"],
    ["", "m_axis_tready", "computer ready: random in T3–T5, T9, T10; constant 1 in T6–T8"],
    ["", "m_axis_tuser", "always 0: damaged frames are never forwarded"],
    ["verdict", "verdict_valid, verdict_mal", "one pulse per judged frame; verdict_mal = 1 if it was malicious"],
    ["CPU config bus", "cfg_wr, cfg_rd, cfg_addr, cfg_wdata, cfg_rdata", "weights (0x100–0x1FF), thresholds (0x001–0x004), mode (0x000), counters (0x020–0x025)"]],
    size=14, row_h=0.5, bold_first_col=True)

# ---- 29 results
s = d.slide(section=S3, notes="What the simulations prove: the hardware matches the Python model exactly, under every condition.")
title(s, "Verification results")
stats = [("600 / 600", "verdicts bit-exact with the Python model", INK), ("197 / 198", "attacks flagged (synthetic data)", GREEN),
         ("0", "false alarms on 402 normal frames", GREEN), ("10 / 10", "functional tests PASS in xrun", AMBER)]
for i, (big, small, c) in enumerate(stats):
    x = 0.6 + i * 3.1
    box(s, x, 1.7, 2.9, 2.6, fill=PALE)
    text(s, x, 1.95, 2.9, 1.2, big, 44, c if c != AMBER else "B5761A", bold=True, font=HEAD, align="c", anchor="m")
    text(s, x + 0.2, 3.2, 2.5, 1.0, small, 15, INK, align="c")
bullets(s, 0.6, 4.7, 12.15, 2.0, [
    "Same 10 tests also pass on the synthesized gate-level netlist (sky130 cells), where real logic gates replace the RTL",
    "12 regressions in total: MAC + firewall at the GMII pins, Tang Nano 9K (RTL + netlist + PC demo), Chameleon96 accelerator",
    "On the real Chameleon96 FPGA: snn_test 10/10 PASS, all 600 verdicts bit-exact, 109,000 frames/s (docs/board_test_cv96.md)"], size=16)

# =================================================================== PART 4
section(4, "Area, power, performance", "Measured numbers: sky130 layout (OpenROAD), FPGA fits (Quartus, nextpnr), and how an SNN compares.",
        "Part 4: all numbers come from tools that ran on this design.")

# ---- 31 headline
s = d.slide(section=S4, notes="snn_classifier placed and routed on SkyWater 130 nm: 1.28 square millimetres, 125 milliwatts "
            "at 100 MHz typical corner, 0 DRC and 0 LVS errors. Timing misses 100 MHz by 0.08 ns at the typical corner.")
title(s, "Headline numbers", sub="snn_classifier placed and routed on SkyWater 130 nm (LibreLane / OpenROAD)")
hl = [("1.28 mm²", "die (1.13 × 1.14 mm), 72,032 cells", INK), ("125 mW", "at 100 MHz, typical corner (vectorless estimate)", PURPLE),
      ("≈ 99 MHz", "typical corner (136 fast, 51 slow)", BLUE), ("28", "clock cycles per decision", GREEN),
      ("0", "multipliers / DSP blocks", "B5761A"), ("0 / 0", "DRC / LVS errors", GREEN)]
for i, (big, small, c) in enumerate(hl):
    x, y = 0.6 + (i % 3) * 4.1, 1.85 + (i // 3) * 2.45
    box(s, x, y, 3.9, 2.2, fill=PALE)
    text(s, x, y + 0.2, 3.9, 1.0, big, 40, c, bold=True, font=HEAD, align="c", anchor="m")
    text(s, x + 0.2, y + 1.25, 3.5, 0.8, small, 15, INK, align="c")

# ---- 32 area breakdown
s = d.slide(section=S4, notes="Where the silicon goes on the full chip. 74 percent of the area is flip-flops, and 91 percent "
            "of those are memory: the 2 KiB packet buffer and the weight table. The SNN's own state is about 3 percent.")
title(s, "Where the area goes", sub="full chip snn_pkt_filter_asic, sky130 synthesis, 1.16 mm²")
doughnut(s, 0.4, 1.45, 7.0, 5.3, ["packet buffer + control", "SNN core (W1 weights + neurons)", "FIFOs", "config + W2", "parser", "encoder"],
         [61.3, 33.9, 2.1, 1.2, 0.8, 0.6], [BLUE, PURPLE, GREY, TEAL, GREEN, AMBER])
box(s, 7.8, 1.6, 4.95, 1.6, fill=PALE)
text(s, 8.0, 1.7, 2.2, 1.4, "74 %", 48, INK, bold=True, font=HEAD, anchor="m")
text(s, 10.0, 1.75, 2.65, 1.35, "sequential (flip-flops); 26 % combinational logic", 15, INK, anchor="m")
box(s, 7.8, 3.4, 4.95, 1.6, fill=PALE)
text(s, 8.0, 3.5, 2.2, 1.4, "91 %", 48, BLUE, bold=True, font=HEAD, anchor="m")
text(s, 10.0, 3.55, 2.65, 1.35, "of all flip-flops are memory (buffer 18,432 + weights 8,192)", 15, INK, anchor="m")
box(s, 7.8, 5.2, 4.95, 1.6, fill=PALE)
text(s, 8.0, 5.3, 2.2, 1.4, "3 %", 48, PURPLE, bold=True, font=HEAD, anchor="m")
text(s, 10.0, 5.35, 2.65, 1.35, "are the SNN's own neuron state (~990 flip-flops)", 15, INK, anchor="m")

# ---- 33 layout
s = d.slide(section=S4, notes="The real placed design, every cell coloured by type: memory flip-flops (blue) and buffers "
            "(grey) outside, the SNN arithmetic (orange) as a dense core.")
title(s, "The real layout: every cell coloured by type")
picture(s, os.path.join(IMG, "sky130_snn_classifier_cell_map.png"), 0.6, 1.35, h=5.45,
        descr="Placement map of snn_classifier on sky130: blue flip-flops, orange combinational logic, grey buffers")
card(s, 6.0, 1.45, 6.75, 5.3, "snn_classifier after place and route", [
    [("30.9 %", {"bold": True, "color": BLUE}), ("  flip-flops (10,256 cells)", {})],
    [("39.8 %", {"bold": True, "color": "B5761A"}), ("  combinational logic (25,447)", {})],
    [("22.6 %", {"bold": True, "color": GREY}), ("  timing-repair buffers (16,704, of them 9,494 hold buffers)", {})],
    [("3.5 %", {"bold": True, "color": RED}), ("  clock tree (1,748)", {})],
    [("3.2 %", {"bold": True}), ("  tap and antenna cells", {})],
    "",
    "Why so many hold buffers? 10,256 flip-flops on one clock give up to 1 ns clock skew; the tool adds small delays to "
    "keep data from racing ahead. Replacing the weight flip-flops by SRAM removes most of them."], body_size=15)

# ---- 34 implementations table
s = d.slide(section=S4, notes="Every implementation we built, side by side.")
title(s, "All implementations compared")
table(s, 0.6, 1.5, 12.15, [2.6, 2.3, 3.3, 2.2, 1.75], [
    ["target", "block", "area / resources", "clock", "power"],
    ["sky130, placed & routed", "snn_classifier", "1.28 mm² die, 72,032 cells", "≈ 99 MHz (tt)", "125 mW"],
    ["sky130, synthesis", "full chip", "1.16 mm², 71,120 cells", "n/a", "n/a"],
    ["Cyclone V (Chameleon96)", "look-aside + HPS", "2,378 ALMs (6 %), 3,080 regs, 0 DSP; board: 109 k frames/s", "110.8 MHz", "not measured"],
    ["Cyclone V (stand-alone)", "in-line, 4 KiB buffer", "5,871 ALMs (14 %), 10,336 regs, 0 DSP", "111.6 MHz", "not measured"],
    ["Tang Nano 9K", "in-line + UART", "6,966 LUT4 (80 %), 2,627 DFF, 0 DSP", "57.6 MHz", "not measured"],
    ["Cadence 90 nm (Genus)", "full chip, 8 ns", "synthesis done; numbers from qor.rpt to add", "", ""]],
    size=14, row_h=0.62)
text(s, 0.6, 6.05, 12.15, 0.8, "The throughput budget: 1 GbE needs one decision per 84 byte-times; we need ~28, so every target meets line rate at its clock.",
     15, GREY, italic=True)

# ---- 35 SNN vs alternatives (numbers)
s = d.slide(section=S4, notes="Same job, different models. Our SNN does roughly 900 additions and no multiplications per "
            "frame. A small CNN on raw header bytes would need on the order of a hundred thousand to a million "
            "multiply-accumulates. Trees and rules are cheaper still but cannot learn temporal patterns.")
title(s, "SNN vs other approaches for the same job")
table(s, 0.6, 1.5, 12.15, [2.6, 3.0, 1.5, 1.4, 1.6, 2.05], [
    ["model", "work per frame", "multipliers", "weights", "latency", "notes"],
    ["Our SNN (64→16→2, T = 8)", "≈ 900 adds / compares", "0", "1.1 KB", "≈ 28 cycles", "event-driven, stateful"],
    ["Same-size int8 MLP", "≈ 1,056 MAC", "32", "1.1 KB", "≈ 5–20 cycles", "one pass, no state"],
    ["Small 1-D CNN on 128 bytes", "≈ 10⁵ – 10⁶ MAC", "many (DSP)", "10–100 KB", "100s–1000s cycles", "learns features itself"],
    ["Decision tree / forest", "≈ 10–20 compares", "0", "small tables", "few cycles", "no time dynamics"],
    ["Rules / ACL", "table look-ups", "0", "TCAM / hash", "1–few cycles", "only known attacks"]],
    size=14, row_h=0.62)
box(s, 0.6, 5.5, 12.15, 1.1, fill=PALE, align="l", size=15, txt=[
    [("Takeaway: ", {"bold": True}), ("for this tiny job an SNN and a same-size MLP do similar work; the SNN avoids all multipliers and adds memory over time. "
      "A CNN costs 100–1000× more operations. Trees and rules are cheapest but cannot learn new temporal patterns.", {})]])

# ---- 36 novelty
s = d.slide(section=S4, notes="Existing SNN intrusion detectors run off the data path, in software or on a neuromorphic chip "
            "fed by software. In-network ML like Taurus targets switches with non-spiking models. Our step is putting the "
            "SNN inside the network card's receive path. Check N3IC and IIsy before claiming this in a paper.")
title(s, "What is new compared with existing work")
table(s, 0.6, 1.5, 6.6, [2.6, 4.0], [
    ["existing work", "how it differs"],
    ["SNN IDS on IBM TrueNorth (Alom & Taha)", "off the data path; 90.12 % accuracy"],
    ["SNN traffic classifiers (Zhou & Li 2020, others)", "software / simulators, no line-rate hardware"],
    ["Taurus (per-packet ML in switches)", "switch pipelines, non-spiking models"],
    ["Generic FPGA SNN accelerators", "image benchmarks, not fused with a MAC"]], size=14, row_h=0.8)
card(s, 7.55, 1.5, 5.2, 5.3, "Our contributions", [
    [("1  ", {"bold": True, "color": "B5761A"}), ("SNN fused into the NIC receive datapath: malicious frames erased before DMA", {})],
    [("2  ", {"bold": True, "color": "B5761A"}), ("event-driven SNN: one pass over active inputs, no multipliers", {})],
    [("3  ", {"bold": True, "color": "B5761A"}), ("hardware rate window feeds flood memory into per-packet spikes", {})],
    [("4  ", {"bold": True, "color": "B5761A"}), ("one engine, three targets, bit-exact with one golden model", {})],
    [("Check before publishing: ", {"bold": True}), ("N3IC (NSDI 2022), IIsy (HotNets 2019)", {})]], body_size=15)

# =================================================================== PART 5
section(5, "Alternatives and next steps", "Other neuron models, other ways to build the whole project, and what to do next.",
        "Part 5: options for the next version, with their trade-offs.")

# ---- 38 alternative neurons
s = d.slide(section=S5, notes="Neuron models from simplest to richest. LIF is the usual sweet spot; IF is cheaper, adaptive "
            "LIF adds memory, Izhikevich is expensive, time-to-first-spike reduces activity.")
title(s, "Alternative neuron models")
table(s, 0.6, 1.5, 12.15, [2.5, 3.6, 3.2, 2.85], [
    ["neuron", "how it works", "hardware per neuron", "trade-off"],
    ["IF (integrate-and-fire)", "like LIF, no leak", "1 register, 1 adder, compare", "cheapest; forgets nothing, noisier"],
    [[("LIF (ours)", {"bold": True, "color": "B5761A"})], "leak 1/4 per step, fire, reset", "register, 2 adders, compare, mux", "good balance; standard choice"],
    ["Adaptive LIF (ALIF)", "threshold rises after each spike", "+ 1 threshold register, + adder", "longer memory: slow scans, bursts"],
    ["Time-to-first-spike", "information in WHEN a neuron fires (1 spike max)", "LIF + a timer", "fewer events, lower power (Zhou & Li 2020)"],
    ["Izhikevich", "2 coupled variables, quadratic", "multipliers, 2 registers", "rich behaviour, much bigger"],
    ["Binary MLP neuron (not spiking)", "XNOR + popcount, one pass", "popcount tree, no state", "fast one-pass alternative (N3IC style)"]],
    size=14, row_h=0.66)

# ---- 39 alternative architectures
s = d.slide(section=S5, notes="Six ways to change the whole system, from cheap improvements of what we have to different "
            "designs entirely.")
title(s, "Alternative project architectures")
alts = [("SRAM + clock gating", "same design, memories in SRAM, weights clock-gated: about −40 to −65 % area and a large power cut", GREEN),
        ("Time-multiplexed neuron", "one LIF unit reused for all 16 neurons: far smaller, 16× more cycles (lower line rate)", BLUE),
        ("Flow-level classifier", "per-flow tables (counts, timings) instead of a 32-frame window: catches slow scans", PURPLE),
        ("Decision trees in the pipeline", "match-action tables as in programmable switches (IIsy, Planter): tiny, very fast, no learning on chip", AMBER),
        ("On-chip STDP learning", "adapt weights in the field with spike-timing rules, from the original snn_stdp design", RED),
        ("Software baseline", "the same model in Linux XDP/eBPF on the CPU: a fair yardstick for the hardware's benefit", TEAL)]
for i, (h_, b, c) in enumerate(alts):
    x, y = 0.6 + (i % 3) * 4.1, 1.6 + (i // 3) * 2.55
    card(s, x, y, 3.9, 2.35, h_, b, badge_label=str(i + 1), badge_fill=c, body_size=15)

# ---- 40 next steps
s = d.slide(dark=True, notes="Summary: the hardware is proven correct in simulation and gate level; next steps are board "
            "tests, real traffic, SRAM and clock gating, and the Cadence numbers.")
text(s, 0.6, 0.5, 12, 0.9, "Where we are, and what comes next", 36, WHITE, bold=True, font=HEAD)
done = ["SNN design, three hardware targets, all bit-exact", "10/10 functional tests in xrun, Questa, gate level",
        "sky130 layout: 1.28 mm², 0 DRC / 0 LVS", "Chameleon96 FPGA: 10/10 board tests PASS, bit-exact"]
todo = ["Live WiFi demo on the Chameleon96; Tang Nano 9K on the perfboard", "Train and test on real traffic (UNSW-NB15, CIC-IDS2017)",
        "SRAM + clock gating; timing at the slow corner", "Cadence 90 nm area / timing / power into the report"]
for col, (hd, items, c) in enumerate([("Done", done, GREEN), ("Next", todo, AMBER)]):
    x = 0.6 + col * 6.25
    text(s, x, 1.6, 5.9, 0.6, hd, 24, c, bold=True, font=HEAD)
    for i, it in enumerate(items):
        badge(s, x, 2.35 + i * 1.05, "", fill=c, d=0.32)
        text(s, x + 0.5, 2.2 + i * 1.05, 5.3, 0.9, it, 17, WHITE)

d.save(OUT)
print("wrote", OUT, "with", d.n, "slides")
