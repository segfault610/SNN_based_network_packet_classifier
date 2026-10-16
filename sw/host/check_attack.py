#!/usr/bin/env python3
"""Verify sw/host/snn_attack.py: every preset it would send is classified the same by the golden model
(the FPGA) as the board's own 'snn_test craft'. Run from the project root:
   .venv/bin/python sw/host/check_attack.py
"""
import os, re, subprocess, sys
ROOT=os.path.dirname(os.path.abspath(__file__))+"/../.."
snd={}
o=subprocess.run([sys.executable,os.path.join(ROOT,"sw/host/snn_attack.py"),"10.0.0.9","all","--dry-run"],
                 capture_output=True,text=True).stdout
for l in o.splitlines():
    m=re.match(r"\s+(\w+)\s+(MALICIOUS|benign)\s+expect\((\d+):(\d+)\)",l)
    if m: snd[m.group(1)]=(m.group(2),m.group(3),m.group(4))
cos=subprocess.run([os.path.join(ROOT,"sw/cv96/tools/cosim/run_cosim.sh"),"craft","all"],
                   capture_output=True,text=True).stdout
brd={}
for l in cos.splitlines():
    m=re.match(r"\s+\d+\s+(MALICIOUS|benign)\s+\((\d+):(\d+)\).*\s(\w+)$",l)
    if m: brd[m.group(4)]=(m.group(1),m.group(2),m.group(3))
diff=[k for k in snd if k in brd and snd[k]!=brd[k]]
for k in diff: print("  DIFF",k,"sender",snd[k],"board",brd[k])
common=set(snd)&set(brd)
print("snn_attack.py vs board craft: %d presets compared, %d differences"%(len(common),len(diff)))
print("RESULT:", "PASS" if not diff and len(common)>=15 else "FAIL")
sys.exit(1 if diff or len(common)<15 else 0)
