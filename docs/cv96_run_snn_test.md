# Running the SNN test on the Chameleon96: quick start

Step by step, starting in the **project root on the laptop**. The board must already boot `cv96_snn.rbf`
(LED2 blinking about once a second). For the meaning of each test and of the output, see
`docs/board_test_cv96.md`.

## 1. Which files go to the board

**To run the test: one file.**

| laptop file (from the project root) | copy to on the board | md5 |
|---|---|---|
| `sw/cv96/tools/snn_test` | `/root/snn_test` | `3f75f06fa17929ce78364e716637ce92` |

The 600 test frames, the weights and the expected answers are built into it. Nothing else is needed: no
vectors, no Python, no libraries (it's a static ARM binary).

**Later, for live WiFi traffic with the kernel module (optional):**

| laptop file | copy to on the board | what it's for | md5 |
|---|---|---|---|
| `sw/cv96/kmod/snn_fw.ko` | `/root/snn_fw.ko` | kernel hook that classifies every frame on `wlan0` | `4ab06c51fc4ed307dfb97bb666c6889f` |
| `sim/vectors/snn_fw.bin` | `/lib/firmware/snn_fw.bin` | the weights the module loads | `73598481c8d214734226345a7cc8db4c` |
| `sw/cv96/tools/snn_fwctl` | `/root/snn_fwctl` | older helper: `id`, `load`, `stats`, `selftest` | `9c7843d0d207f3c0f3bb8c63db200d87` |
| `sim/vectors/cfg.txt`, `frames.txt`, `expected.txt` | `/root/` | only for `snn_fwctl load` / `selftest` | |

**Already on the board, no copy needed:** the FPGA image, `fpga/cv96_snn/output_files/cv96_snn.rbf` (md5
`dd5c44c27549b5104b585d2b89e0aee1`). To check, compare with `md5sum` of the `.rbf` your U-Boot loads.

## 2. (Only if you changed the code) rebuild and pre-test on the laptop

```bash
make -C sw/cv96/tools snn_test          # cross-compiles with the Yocto toolchain -> sw/cv96/tools/snn_test
sw/cv96/tools/cosim/run_cosim.sh        # same program against the FPGA's RTL (Verilator): expect RESULT: PASS (10 of 10)
```
`snn_test` is git-ignored (a build product). After a fresh `git clone`, run the `make` line once.

## 3. Copy the file to the board

Pick whichever works.

**A. Over the network** (the board has WiFi up; find its address on the board with `ip -4 addr show wlan0`):
```bash
scp sw/cv96/tools/snn_test root@<board-ip>:/root/
```

**B. USB stick** (no network needed):
```bash
# laptop
cp sw/cv96/tools/snn_test /media/$USER/<your-stick>/ && sync
```
```sh
# board (serial console), stick in the free USB port
mkdir -p /mnt/usb && mount /dev/sda1 /mnt/usb      # check the name with: dmesg | tail  (could be sdb1)
cp /mnt/usb/snn_test /root/ && umount /mnt/usb
```

**C. SD card** (board powered off):
```bash
# laptop, SD card inserted
lsblk                                              # find the card's root filesystem partition (ext3/ext4, the large one)
sudo mkdir -p /mnt/sd && sudo mount /dev/sdX2 /mnt/sd   # X and the partition number from lsblk
sudo cp sw/cv96/tools/snn_test /mnt/sd/root/ && sync && sudo umount /mnt/sd
```

## 4. Run it on the board

Log in on the serial console as `root`, then:

```sh
# 1) the FPGA image is loaded and the bridge to it is open
cat /sys/class/fpga_manager/fpga0/state                                          # expect: operating
for b in /sys/class/fpga_bridge/*; do echo "$(cat $b/name) $(cat $b/state)"; done   # lwhps2fpga ... enabled
#    if the lwhps2fpga bridge says "disabled": stop here (an access could hang the board), see §6

# 2) nothing else may use the accelerator at the same time
lsmod | grep snn_fw && rmmod snn_fw

# 3) the file arrived intact
cd /root
md5sum snn_test                                   # 3f75f06fa17929ce78364e716637ce92
chmod +x snn_test

# 4) run
./snn_test stats        # quick check: ID 0x534e4e32, STATUS, counters
./snn_test              # all 10 tests C1..C10, a few seconds
./snn_test demo         # replays normal traffic, then the SYN flood: watch LED1
./snn_test demo 400     # the same, slower (400 ms per frame)
./snn_test C3           # just one test (C1 ... C10)
```

## 5. What you should see

- `./snn_test` ends with:
  ```
  ============================================================
   RESULT: PASS (10 of 10 tests passed)
  ============================================================
  ```
  Each test prints a line or two and `PASS Cn`. C3 must report `malicious 197, benign 403 | ... TP=197 FP=0 TN=402 FN=1`.
- `./snn_test demo` prints one line per frame. From frame 47 on (the SYN flood) the lines say `MALICIOUS`, and
  **LED1 lights up** with them. Before that, LED1 stays dark.
- LED2 keeps blinking the whole time: that's only the "design is alive" heartbeat.

Please send back:
- the complete output of `./snn_test` (copy it from the serial terminal);
- whether LED1 lit up in `demo`.

On a failure, the `[ERR]` lines say exactly which frame or register differed.

## 6. If something goes wrong

| what you see | do this |
|---|---|
| `-sh: ./snn_test: not found` or `Permission denied` | `chmod +x snn_test`; check `md5sum` (a broken copy also gives "not found") |
| `open /dev/mem (run as root)` | log in as `root` |
| `no SNN accelerator at 0xff210000 (ID reads 0x...)` | the old RBF is loaded: reboot with `cv96_snn.rbf` |
| it hangs at the first line | the lwhps2fpga bridge is disabled. Reboot, stop in U-Boot, run `bridge enable`, then `boot` (to make it permanent, add `bridge enable;` to the U-Boot boot command). Your existing LED PIO setup already needs the same bridge, so it is normally on |
| `snn_fw.ko is loaded ...` | `rmmod snn_fw` |
| tests fail with `[ERR]` | send me the whole output |

## 7. After it passes: live WiFi traffic (optional)

With the optional files from §1 copied:
```sh
insmod /root/snn_fw.ko iface=wlan0 drop=0     # classify every received WiFi frame, don't drop yet
cat /proc/snn_fw                              # seen / malicious / dropped / timeouts ...
```
Then attack the board from the laptop (`sudo hping3 -S --flood -p 80 <board-ip>`) and watch LED1 and `/proc/snn_fw`.
Enable dropping with `echo "drop 1" > /proc/snn_fw`. Remove it with `rmmod snn_fw`.
Details: `docs/chameleon96_deploy.md`.
