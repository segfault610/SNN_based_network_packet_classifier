# How to test

## 0. Simulation (no hardware)

```bash
sim/tang9k/run.sh              # Tang Nano 9K: rtl | gl (post-synthesis netlist) | host (tang_demo.py vs fake board) | all
sim/cv96/run.sh                # Chameleon96: lookaside (the accelerator in the RBF) | avmm | all
sim/asic/run.sh                # ASIC / in-line datapath: filter | stress | mac | suite | suite-gl | all
sim/run_all.sh                 # all 12 regressions
```
Add `gui` as the mode (e.g. `sim/tang9k/run.sh gui`) to open the vsim GUI with waves.
Full logs land in `sim/<target>/out/*.log`. The ASIC functional test table and its xrun usage are in
`docs/functional_verification.md`.

To try the PC demo script by hand against the software stand-in board:
```bash
python3 sw/tang9k/fake_tang.py &   # prints /dev/pts/N
python3 sw/tang9k/tang_demo.py --port /dev/pts/N
```

## 1. Tang Nano 9K: in-line firewall (the ASIC architecture on real silicon)

What runs on it: the full `snn_pkt_filter` (store-and-forward buffer, parser,
encoder, SNN, forward/drop) at 27 MHz. The PC's USB-UART (1 Mbaud, SLIP)
stands in for the PHY: the PC sends frames in, and the FPGA sends back only the
frames it forwards, plus one verdict per frame.

```bash
fpga/tang9k/build.sh           # yosys + nextpnr-himbaechel + apicula -> tang9k_snn.fs (~4 min)
openFPGALoader -b tangnano9k fpga/tang9k/tang9k_snn.fs        # SRAM (lost on power-off)
openFPGALoader -b tangnano9k -f fpga/tang9k/tang9k_snn.fs     # or write to flash
ls /dev/ttyUSB*                # the BL702 shows two ports; the UART is usually /dev/ttyUSB1
python3 sw/tang9k/tang_demo.py --port /dev/ttyUSB1               # golden vectors: expect RESULT: PASS
```

LEDs (left→right = led_n[0..5]): 0 malicious frame, 1 heartbeat (~1.2 s),
2 frame forwarded, 3 frame blocked, 4 UART RX activity, 5 config written.
S1 = reset.

**Checks**
1. Heartbeat blinks: the bitstream loaded and the 27 MHz clock is running.
2. `link OK ... TH1 readback = 256`: the UART and SLIP path work.
3. `verdicts bit-exact vs golden model: True` and `forwarded frames identical: True`:
   the hardware matches simulation exactly.

**Real attack traffic (replayed):** capture your own attacks on loopback and replay them through the FPGA:
```bash
sudo tcpdump -i lo -w /tmp/attack.pcap &
sudo nmap -sX -p 1-2000 127.0.0.1 ; sudo nmap -sN -p 1-2000 127.0.0.1
sudo hping3 -S -c 3000 --faster -p 80 127.0.0.1 ; ping -c 50 127.0.0.1
sudo pkill tcpdump
python3 sw/tang9k/tang_demo.py --port /dev/ttyUSB1 --pcap /tmp/attack.pcap
```
(Linux loopback pcaps use the Ethernet link type with zero MACs, so they replay as-is.)

**Troubleshooting**
- If `link OK` never appears, try the other ttyUSB and check `dmesg`.
- If the BL702 can't do 1 Mbaud, rebuild with `CLKS_PER_BIT=234` (115200 baud) and pass `--baud 115200`.

## 2. Chameleon96: real network, real Linux (look-aside)

Full steps: `docs/chameleon96_deploy.md`. Short version:
1. Boot with `fpga/cv96_snn/output_files/cv96_snn.rbf`, using the same file name/location as your current `cv96.rbf`. It's compressed, like yours.
2. `./snn_fwctl id` → `0x534e4e32`. Then `./snn_fwctl load cfg.txt` and `./snn_fwctl selftest frames.txt expected.txt` → `RESULT: PASS`. That proves the FPGA is bit-exact on the board.
3. `insmod snn_fw.ko iface=wlan0 drop=0` and attack from the laptop (`hping3`, `nmap -sX/-sN`). Watch `/proc/snn_fw` and LED1.
4. `echo "drop 1" > /proc/snn_fw`: malicious frames are now freed right after the WiFi driver.

## Which board for what

| | Tang Nano 9K | Chameleon96 |
|---|---|---|
| shows | the **in-line NIC datapath** (what the ASIC is) | the **system**: real WiFi, real Linux, real attacks |
| traffic | replayed (vectors / pcap) over UART | live, over the USB WiFi adapter |
| where packets stop | inside the FPGA before reaching the PC | in the kernel, right after the driver |

Use both: the Tang shows the hardware mechanism, and the Chameleon96 shows it working on a live network.

### ENC28J60 / ESP8266?
* **ENC28J60** (SPI 10BASE-T MAC+PHY): yes, that's the natural next step for the
  Tang. An SPI master in the FPGA pulls received frames out of the ENC28J60
  buffer straight into `snn_pkt_filter`, giving a real Ethernet wire into the
  in-line firewall. It needs an ENC28J60 SPI controller in HDL (~1–2 days).
  The module runs on 3.3 V, so use the Tang's 3.3 V bank pins.
* **ESP8266:** no. It's a WiFi SoC with its own TCP/IP stack; with AT firmware
  you get sockets, not raw frames. Promiscuous mode only gives 802.11 metadata
  and truncated headers, and it can't forward.
