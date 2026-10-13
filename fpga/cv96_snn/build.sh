#!/usr/bin/env bash
# Regenerate Platform Designer system and compile the Chameleon96 SNN design -> output_files/cv96_snn.rbf
set -e
cd "$(dirname "$0")"
export PATH=$HOME/intelFPGA_lite/20.1/quartus/sopc_builder/bin:$HOME/intelFPGA_lite/20.1/quartus/bin:$PATH
qsys-generate QSYS/CV96_QSYS.qsys --synthesis=VERILOG --output-directory=QSYS/CV96_QSYS --search-path="$PWD/QSYS/**/*,\$"
quartus_sh --flow compile led_blink_linux
quartus_cpf -c -o bitstream_compression=on output_files/led_blink_linux.sof output_files/cv96_snn.rbf
echo "RBF: $PWD/output_files/cv96_snn.rbf"
