#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Distil the big Genus reports into a one-screen timing summary per variant:
# clock / Fmax, WNS (worst slack), TNS, #violating paths, and the worst path.
# Pure shell + awk - runs locally, no Cadence tools needed.
#
#   from asic/:  scripts/timing_summary.sh
#
# For each variant it reads, preferring the fuller re-run reports when present:
#   WNS/TNS/#viol : reports/qor_timing.rpt   else  reports/qor.rpt      (report_qor = whole design)
#   worst path    : reports/timing_setup_max*.rpt  else  reports/timing.rpt
# Writes  out/<DESIGN>/syn_<V>/reports/timing_summary.txt   (one per variant)
#  and    out/<DESIGN>/timing_summary.txt                   (all three together)
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")/.."                      # asic/
DESIGN="${DESIGN:-snn_pkt_filter_asic}"
OUT="out/$DESIGN"
ALL="$OUT/timing_summary.txt"
: > "$ALL"

# nominal clock period (ps) fallback if qor can't be parsed
declare -A NOM=( [fast]=5000 [optimal]=8000 [slow]=12000 )

summarise() {               # $1 = variant
  local v="$1" rpt="$OUT/syn_$v/reports" out
  out="$rpt/timing_summary.txt"
  [ -d "$rpt" ] || { echo "skip $v: no reports dir"; return; }

  # pick the QoR file (re-run preferred) and the worst-path file
  local qor path
  qor="$rpt/qor.rpt";  [ -f "$rpt/qor_timing.rpt" ] && qor="$rpt/qor_timing.rpt"
  path=""; path=$(ls -1 "$rpt"/timing_setup_max*.rpt 2>/dev/null | head -1)
  [ -z "$path" ] && path="$rpt/timing.rpt"

  # ---- clock period (ps): the "clk <period>" line (two fields) in qor
  local period; period=$(awk '$1=="clk" && NF==2 {print $2; exit}' "$qor" 2>/dev/null)
  [ -z "$period" ] && period="${NOM[$v]}"
  # ---- cost-group row:  clk  <slack> <tns> <violating>
  local wns tns viol
  read -r wns tns viol < <(awk '$1=="clk" && NF>=4 {print $2, $3, $4; exit}' "$qor" 2>/dev/null)
  : "${wns:=n/a}" "${tns:=n/a}" "${viol:=n/a}"
  local fmax; fmax=$(awk -v p="$period" 'BEGIN{ if(p>0) printf "%.1f", 1000000.0/p; else print "n/a"}')

  # ---- worst path (first Path block) from the path report
  local sp ep dp slk
  sp=$(awk '/Startpoint:/{print $NF; exit}'  "$path" 2>/dev/null)
  ep=$(awk '/Endpoint:/{print $NF; exit}'    "$path" 2>/dev/null)
  dp=$(awk '/Data Path:/{print $NF; exit}'   "$path" 2>/dev/null)
  slk=$(awk '/Slack:/{print $NF; exit}'      "$path" 2>/dev/null)

  {
    echo "=================================================================="
    echo " $DESIGN  -  variant: $v"
    echo "=================================================================="
    echo " Clock period        : ${period} ps  (${fmax} MHz target)"
    echo " WNS (worst slack)   : ${wns} ps     [>=0 => timing MET; this is report_qor's critical-path slack]"
    echo " TNS (total neg slack): ${tns} ps"
    echo " Violating paths     : ${viol}        [whole design, report_qor - NOT capped at 10]"
    echo " Worst path source   : $path"
    if [ -n "$sp" ]; then
      echo " Worst path:"
      echo "   startpoint        : $sp"
      echo "   endpoint          : $ep"
      echo "   data-path delay   : ${dp} ps"
      echo "   path slack        : ${slk} ps"
    else
      echo " Worst path          : no constrained path list in $path"
      echo "                       (re-run:  TVARIANT=$v genus -no_gui -files scripts/genus_timing.tcl)"
    fi
    echo
  } | tee "$out" >> "$ALL"
}

for v in fast optimal slow; do summarise "$v"; done
echo "wrote per-variant reports/timing_summary.txt and combined $ALL"
