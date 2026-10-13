#!/usr/bin/env bash
# Every simulation in the project: sim/run_all.sh
#   per target:  sim/asic/run.sh   sim/tang9k/run.sh   sim/cv96/run.sh   (each takes a mode, see its header)
cd "$(dirname "$0")"
pass=0; fail=0
run() { echo "=== $1"; out=$("${@:2}" 2>&1); echo "$out" | grep -E "RESULT" | sed 's/^/   /'
        if echo "$out" | grep -q "RESULT: FAIL" || ! echo "$out" | grep -q "RESULT: PASS"; then
          fail=$((fail+1)); echo "$out" | grep -E "ERR|Error|Traceback" | head -5 | sed 's/^/   /'
        else pass=$((pass+1)); fi; }
run "ASIC: in-line filter, bit-exact"            asic/run.sh filter
run "ASIC: in-line filter, stress"               asic/run.sh stress
run "ASIC: MAC + filter (GMII)"                  asic/run.sh mac
run "ASIC: top T1-T10 (RTL)"                     asic/run.sh suite
run "ASIC: top T1-T10 (sky130 gate-level)"       asic/run.sh suite-gl
run "Tang Nano 9K: top (UART/SLIP), RTL"         tang9k/run.sh rtl
run "Tang Nano 9K: post-synthesis gate-level"    tang9k/run.sh gl
run "Tang Nano 9K: host demo vs fake board"      tang9k/run.sh host
run "Chameleon96: look-aside accelerator"        cv96/run.sh lookaside
run "Chameleon96: Avalon-MM in-line wrapper"     cv96/run.sh avmm
run "pcap loader round trip"                     ../.venv/bin/python ../model/test_pcap_io.py
run "snn_stdp saturation fix"                    bash -c "iverilog -g2005 -o /tmp/stdp_\$\$.vvp -s tb_snn_stdp ../snn_stdp/tb/tb_snn_stdp.v ../snn_stdp/src/snn_stdp.v && vvp -n /tmp/stdp_\$\$.vvp; rm -f /tmp/stdp_\$\$.vvp"
echo "=== $pass passed, $fail failed"
