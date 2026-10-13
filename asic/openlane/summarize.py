#!/usr/bin/env python3
"""Turn a LibreLane run into a short Markdown report (+ GitHub annotations).
   summarize.py <run_dir> <design> <out.md>"""
import json, os, sys, glob

run, design, out = sys.argv[1], sys.argv[2], sys.argv[3]
m = {}
p = os.path.join(run, "final", "metrics.json")
if os.path.exists(p):
    m = json.load(open(p))

ROWS = [
    ("Die area (um^2)", "design__die__area"),
    ("Core area (um^2)", "design__core__area"),
    ("Std-cell area (um^2)", ("design__instance__area__stdcell", "design__instance__area")),
    ("Cell instances", ("design__instance__count__stdcell", "design__instance__count")),
    ("Utilisation", "design__instance__utilization"),
    ("Setup WNS, typical (ns)", "timing__setup__ws__corner:nom_tt_025C_1v80"),
    ("Setup WNS, worst corner (ns)", "timing__setup__ws"),
    ("Hold WNS, worst corner (ns)", "timing__hold__ws"),
    ("Setup violations (count)", "timing__setup_vio__count"),
    ("Hold violations (count)", "timing__hold_vio__count"),
    ("Total power (W)", "power__total"),
    ("Wire length (um)", "route__wirelength"),
    ("Routing DRC errors", "route__drc_errors"),
    ("Magic DRC errors", "magic__drc_error__count"),
    ("KLayout DRC errors", "klayout__drc_error__count"),
    ("LVS errors", "design__lvs_error__count"),
    ("Antenna violations", "antenna__violating__nets"),
]
lines = [f"## {design}: sky130 LibreLane results", ""]
if not m:
    lines.append("No final metrics (flow did not finish). See flow.log / error summary.")
else:
    lines += ["| metric | value |", "|---|---|"]
    for name, keys in ROWS:
        for key in (keys if isinstance(keys, tuple) else (keys,)):
            if key in m:
                lines.append(f"| {name} | {m[key]} |")
                break
open(out, "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
# one GitHub annotation with the headline numbers
if m:
    keys = ["design__instance__area", "timing__setup__ws", "timing__hold__ws",
            "power__total", "magic__drc_error__count", "design__lvs_error__count"]
    msg = ", ".join(f"{k}={m[k]}" for k in keys if k in m)
    print(f"::notice title={design} metrics::{msg}")
