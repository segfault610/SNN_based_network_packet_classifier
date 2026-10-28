#!/usr/bin/env bash
# Launch the RTL testbench (tb_snn_asic, tests T1..T10) in Xcelium with the
# SimVision GUI and waveforms.
#
# Why the manual `xrun -gui -f scripts/xrun_rtl.f ...` failed with
#   "Cannot find the provided file ../../rtl/sync_fifo.v":
# the .f file lists its sources relative to the .f file's own location
# (asic/scripts/), so xrun must be given -F (uppercase: paths relative to the
# file) and NOT -f (lowercase: paths relative to the current directory).
# From asic/, `-f` turns ../../rtl into <repo>/../rtl, which is outside the repo.
#
# Usage (from anywhere):
#   asic/scripts/sim_gui.sh
# Extra xrun args are forwarded, e.g.:  asic/scripts/sim_gui.sh -covoverwrite
set -euo pipefail
cd "$(dirname "$0")/.."                        # -> asic/
VEC="$(cd ../sim/vectors 2>/dev/null && pwd || true)"

ARGS=(-gui -F scripts/xrun_rtl.f -input scripts/sim_gui_waves.tcl)
[ -n "$VEC" ] && ARGS+=(+VEC_DIR="$VEC")

echo "+ xrun ${ARGS[*]} $*"
exec xrun "${ARGS[@]}" "$@"
