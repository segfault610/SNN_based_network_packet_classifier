# Chameleon96 deployment (look-aside SNN firewall, USB WiFi)

## Why look-aside on this board

```
 TP-Link USB WiFi ─USB─► HPS USB host ─► rtl8xxxu/mac80211 ─► wlan0 ─► [snn_fw.ko rx_handler] ─► IP stack ─► sockets/apps
                                                                       │  128-B header + length   ▲ verdict
                                                                       ▼  (LW H2F bridge)         │
                                                              FPGA: snn_lookaside_avmm (same parser/encoder/SNN as the in-line filter)
```

The NIC is on the HPS side, so every frame lands in kernel memory before the
FPGA can see it. The hook is placed as early as Linux allows: the netdev
`rx_handler`, which runs right after the driver hands the frame up and before
the IP stack, netfilter, sockets or any user-space program. A malicious frame
is freed there, so nothing above the driver ever processes it. The in-line
(pre-host) variant of the same classifier is shown on the Tang Nano 9K and in
`rtl/eth_mac_1g_snn_fifo.v`, and that is the version for the ASIC.

Only the first 128 bytes (enough for VLAN+IPv4-with-options+TCP) plus the
true frame length cross the bridge. Verdicts are bit-identical to the in-line
filter (`sim/run_lookaside.sh`).

## Files

| file | what |
|---|---|
| `fpga/cv96_snn/output_files/cv96_snn.rbf` | FPGA image: your led_blink_linux system + `snn_0` at LW offset 0x10000 (phys **0xFF210000**), IRQ f2h #1. HPS handoff unchanged, so the existing preloader/U-Boot keep working |
| `sw/kmod/snn_fw.ko` | kernel module, built against your Yocto kernel `6.18.2-altera` |
| `sw/tools/snn_fwctl` | static ARM tool: `id`, `load`, `stats`, `selftest` |
| `sim/vectors/snn_fw.bin` | weights for the module → `/lib/firmware/snn_fw.bin` |
| `sim/vectors/{cfg,frames,expected}.txt` | weights (text) + golden vectors for the on-board self-test |
| `sw/yocto/meta-snn` | optional layer to put all of the above into the image |

Rebuild: `fpga/cv96_snn/build.sh` (≈6 min), `make -C sw/kmod`, `make -C sw/tools`.

## Bring-up

```sh
# host
scp fpga/cv96_snn/output_files/cv96_snn.rbf  root@board:/boot/   # or wherever your U-Boot loads the rbf from
scp sw/kmod/snn_fw.ko sw/tools/snn_fwctl sim/vectors/{cfg,frames,expected}.txt root@board:/root/
scp sim/vectors/snn_fw.bin root@board:/lib/firmware/
# board (after reboot with the new rbf; LW bridge must be enabled, as for the LED PIO)
./snn_fwctl id                                   # -> SNN accelerator ID 0x534e4e32
./snn_fwctl load cfg.txt
./snn_fwctl selftest frames.txt expected.txt     # hardware must be bit-exact: RESULT: PASS
insmod snn_fw.ko iface=wlan0 drop=0              # monitor mode first
cat /proc/snn_fw
```

Attack traffic from a laptop on the same WiFi (only against your own board):

```sh
sudo hping3 -S --flood -p 80 <board-ip>          # SYN flood      -> rate features
sudo nmap -sX -p 1-1000 <board-ip>               # Xmas scan
sudo nmap -sN <board-ip>                         # NULL scan
sudo hping3 --icmp --flood <board-ip>            # ICMP flood
sudo hping3 -S -a <board-ip> -p 80 <board-ip>    # land attack
```

Watch LED1 flash and `/proc/snn_fw` count up. Then `echo "drop 1" > /proc/snn_fw`
and confirm, for example, that `tcpdump -i wlan0` no longer sees the scan packets.
tcpdump taps in before rx_handler, so it still sees them. Use the counters, or
`ss -s` / service logs, to show they never reach the stack.

Notes
* **Fail-open:** if the accelerator doesn't answer within `poll_max` reads, the
  frame passes and `timeouts` increments.
* The weights are trained on synthetic traffic. Run in monitor mode on real WiFi
  traffic first and check false positives. Retrain with real captures via
  `model/pcap_io.py` (see the README).
* rx_handler is exclusive per interface. If wlan0 is bridged, the module refuses
  to load.
