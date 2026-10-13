# Shared settings for sim/<target>/run.sh (sourced, not executed).
# Each target keeps its Questa work libraries, transcripts and logs in sim/<target>/out/ (git-ignored).
set -e
SIM=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$SIM/.." && pwd)
RTL=$ROOT/rtl
VEC=$SIM/vectors                       # written by model/export.py
CORE="$RTL/sync_fifo.v $RTL/pkt_parser.v $RTL/spike_encoder.v $RTL/snn_core.v $RTL/snn_classifier.v"
OSS=/opt/oss-cad-suite
PY=$ROOT/.venv/bin/python
[ -x "$PY" ] || PY=python3
OUT=$TGT/out
mkdir -p "$OUT"
cd "$OUT"                              # transcript / modelsim.ini land here

[ -f "$VEC/cfg.txt" ] || { echo "no vectors: run  .venv/bin/python model/export.py  first"; exit 1; }

# newlib <name>            fresh Questa library $OUT/work_<name>
newlib() { rm -rf "work_$1"; vlib "work_$1" >/dev/null; }
# sim <lib> <top> <log> <grep-regex> [vsim args]   batch run, full log to $OUT/<log>, filtered to stdout
sim() {
  local lib=$1 top=$2 log=$3 re=$4; shift 4
  vsim -c -lib "work_$lib" "$@" "$top" -do "run -all; quit -f" > "$log" 2>&1 || true
  grep -E "$re" "$log" | sed 's/^# *//' || true
}
# usage <text>             print the header comment of the calling script
usage() { sed -n '2,/^[^#]/p' "$0" | sed '$d'; exit 1; }
