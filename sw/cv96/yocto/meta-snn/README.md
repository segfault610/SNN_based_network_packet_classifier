# meta-snn

Add to `build/conf/bblayers.conf`, then in `local.conf`:

    IMAGE_INSTALL:append = " snn-fw snn-fwctl"

`snn-fw` installs `snn_fw.ko` + `/lib/firmware/snn_fw.bin`; `snn-fwctl` installs
`/usr/bin/snn_fwctl` and the golden vectors in `/usr/share/snn/`.
Quicker alternative without rebuilding the image: copy the prebuilt
`sw/cv96/kmod/snn_fw.ko`, `sw/cv96/tools/snn_fwctl` (static) and `sim/vectors/*` to the board.
