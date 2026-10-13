#!/usr/bin/env bash
# Full regression: every RTL variant against the golden model + data-path self-tests.
cd "$(dirname "$0")"
pass=0; fail=0
run() { echo "=== $1"; out=$("${@:2}" 2>&1); echo "$out" | grep -E "RESULT" | sed 's/^# */   /'; 
        if echo "$out" | grep -q "RESULT: FAIL" || ! echo "$out" | grep -q "RESULT: PASS"; then fail=$((fail+1)); else pass=$((pass+1)); fi; }
run "in-line filter (bit-exact + stress)"     ./run_filter.sh
run "MAC + filter system (GMII)"              ./run_mac.sh
run "Avalon-MM in-line wrapper"              ./run_avmm.sh
run "look-aside accelerator (Chameleon96)"   ./run_lookaside.sh
run "Tang Nano 9K top (UART/SLIP)"           ./run_tang9k.sh
run "pcap loader round trip"                 ../.venv/bin/python ../model/test_pcap_io.py
run "snn_stdp saturation fix"                bash -c "iverilog -g2005 -o /tmp/stdp_\$\$.vvp -s tb_snn_stdp ../snn_stdp/tb/tb_snn_stdp.v ../snn_stdp/src/snn_stdp.v && vvp -n /tmp/stdp_\$\$.vvp"
echo "=== $pass passed, $fail failed"
rm -rf work work_mac work_avmm work_la work_tang
