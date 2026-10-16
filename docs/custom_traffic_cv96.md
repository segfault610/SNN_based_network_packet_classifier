# Testing your own packets on the Chameleon96

The ten built-in tests (C1–C10) replay a fixed recording, so passing them shows only that the FPGA reproduces the
model on those 600 frames. This page shows how to send **any packet you want** through the FPGA: built from
presets, edited field by field, pasted as hex, taken from a capture file, or live from the WiFi interface. It also
covers how to see what the network looked at and why it decided.

## 1. What the accelerator inspects

| looked at | not looked at |
|---|---|
| the **first ≤ 128 bytes** of the frame: Ethernet type (+ one VLAN tag), the whole **IPv4 header** (length, flags, fragment offset, TTL, protocol, addresses), the **TCP/UDP/ICMP header** (ports, flags, data offset, window, ICMP type) | the **payload content**: only its *length* matters |
| the frame's **true length** | MAC addresses |
| **memory of the last 32 frames:** how many were pure SYNs, how many were ping requests | anything older than 32 frames; per-connection state |

These are turned into 64 yes/no answers. Examples:
- "TCP?", "SYN set?", "TTL above 128?", "IP length ≤ 40?", "destination port 0?", "TCP options present?";
- "≥ 8 SYNs among the last 32 frames?", "source = destination?", "source is 127.x?".

The full list is in `docs/design.md` §4. Exact addresses and port numbers are not used, only their *classes*
(well-known / registered / high port, bogon source, broadcast destination, …). The SNN weighs the 64 answers; no rule
is written anywhere.

## 2. The commands (on the board, as root)

You need the current `snn_test` (md5 `607769e7804f0dd491374c82145cbb50`; copy it as in `docs/cv96_run_snn_test.md`).
`rmmod snn_fw` first, if it is loaded.

| command | what it does |
|---|---|
| `./snn_test craft list` | lists the packet presets and the editable fields |
| `./snn_test craft <preset> [field=value …]` | builds the packet(s), sends each through the FPGA, prints header + verdict |
| `./snn_test craft all` | every preset once |
| `./snn_test frame <hex bytes>` | classifies one raw Ethernet frame (spaces/colons allowed; `-` reads hex from stdin) |
| `./snn_test pcap <file.pcap> [max]` | classifies every frame of a capture (classic pcap; Ethernet or Linux "cooked" link type) |
| `./snn_test sniff [wlan0] [count]` | classifies **live received** frames from an interface; Ctrl-C prints a summary. It only watches; nothing is dropped |

Add `hex` to any of them to also print each frame's bytes. Add `noflush` to keep the 32-frame SYN/ping memory from
earlier commands; by default each command starts with that memory empty.

**Every output line** has the same form:
```
   1  benign    (8:0)  TCP 192.168.1.23:51234 > 93.184.216.34:443 [S] ttl=64 win=64240 opts=12B 66B
   │  │          │     └ the header, decoded here in software so you can see what was judged
   │  │          └ spikes of the benign : malicious output neuron (0-8 each, 8 time steps)
   │  └ the FPGA's verdict (LED1 flashes on MALICIOUS)
   └ frame number
```

## 3. Presets and fields

Normal traffic: `syn` `ack` `data` `fin` `ping` `dns` `arp`.

Attacks: `synflood` (40 bare SYNs) `synscan` `xmas` `null` `finscan` `ackscan` `udpscan` (25 ports each) `port0`
`land` `pingflood` (40 × 1000 B) `smurf` `bogon` `lowttl` `tinyfrag` `malformed`.

Fields you can override:

| field | example | meaning |
|---|---|---|
| `ttl=` | `ttl=200` | IP time-to-live |
| `sport=` `dport=` | `dport=0` | ports |
| `flags=` | `flags=SF` | TCP flags as letters: F S R P A U (or `flags=none`) |
| `opts=` | `opts=0` | bytes of TCP options (0–40; real clients send 12–20) |
| `win=` | `win=512` | TCP window |
| `payload=` | `payload=1000` | payload length in bytes (filled with letters) |
| `src=` `dst=` | `src=127.0.0.5` | IP addresses |
| `df=` `mf=` `foff=` `ihl=` | `mf=1` | IP flags, fragment offset, header length |
| `icmp=` `proto=` | `proto=udp` | ICMP type, protocol |
| `count=` `inc=1` | `count=40 inc=1` | number of packets; `inc=1` raises the destination port by 1 per packet (a scan) |

## 4. Experiments to try (with the results the FPGA should give)

These results come from the co-simulation of the same program on the FPGA's RTL (§6). The board must print the same
verdicts.

```sh
./snn_test craft all                          # 7 normal presets benign, all 15 attack presets MALICIOUS
./snn_test craft syn                          # benign (8:0): a normal client SYN
./snn_test craft syn ttl=200                  # MALICIOUS: same SYN, but TTL 200
./snn_test craft syn opts=0                   # MALICIOUS: same SYN without TCP options (as flood tools send)
./snn_test craft syn sport=4000               # benign: the exact source port doesn't matter
./snn_test craft syn win=512                  # benign: the window alone doesn't matter
./snn_test craft syn dport=0                  # MALICIOUS: port 0
./snn_test craft syn src=127.0.0.5            # MALICIOUS: impossible source address
./snn_test craft syn flags=FPU                # MALICIOUS: Xmas flags
./snn_test craft ping                         # benign
./snn_test craft ping payload=1000            # MALICIOUS: oversized ping, like a ping flood
./snn_test craft dns dport=0                  # MALICIOUS
./snn_test craft data ttl=1                   # MALICIOUS: TTL-1 evasion trick
./snn_test craft synflood                     # 40 x MALICIOUS
./snn_test craft syn count=40                 # 40 x benign  <- a known blind spot, see §5
```

With LED1 in view, `./snn_test craft synflood` and `./snn_test craft pingflood` make it flicker.

### Real attacks from the laptop (WiFi up)

Watch live:
```sh
# board
./snn_test sniff wlan0
```
```bash
# laptop (only against your own board)
ping -c 5 <board-ip>                          # benign
sudo hping3 -S -p 80 -c 50 --faster <board-ip>    # SYN flood
sudo nmap -sX -p 1-100 <board-ip>             # Xmas scan
sudo nmap -sN -p 1-100 <board-ip>             # NULL scan
sudo hping3 --icmp -d 1000 -c 30 --faster <board-ip>   # big pings
```

Or record first and classify afterwards:
```sh
# board
tcpdump -i wlan0 -w /root/cap.pcap            # Ctrl-C after the attacks
./snn_test pcap /root/cap.pcap
```
A pcap made on the laptop (`sudo tcpdump -i <iface> -w cap.pcap`) works too; copy it over. For pcapng files, convert
with `editcap -F pcap in.pcapng out.pcap`.

## 5. Why it decided, and its limits (on the laptop)

`model/explain_frame.py` runs the golden model, which is bit-identical to the FPGA. For any frame it prints:
- the parsed header;
- the "yes" answers;
- the spike counts;
- which answers pushed the decision, by switching each "yes" off in turn.

```bash
./snn_test craft syn ttl=200 hex                       # on the board: copy the 'hex:' line
.venv/bin/python model/explain_frame.py <paste hex>    # on the laptop
.venv/bin/python model/explain_frame.py --vector 47    # a frame of the test recording
.venv/bin/python model/explain_frame.py --pcap cap.pcap --index 3
.venv/bin/python model/explain_frame.py <hex> --syn 20 # pretend 20 SYNs were seen in the last 32 frames
```

Example, `syn ttl=200`:
```
output spikes in 8 time steps: benign 0, malicious 4  ->  MALICIOUS
what drove the decision (each 'yes' switched off in turn; + = it pushed towards MALICIOUS):
   +1020  ttl_gt128      towards MALICIOUS   <- alone flips the verdict (would be 4:2)
    -974  ip_df          towards benign
    +456  doff_gt5       towards MALICIOUS
  ...
```

**Limits these tools reveal**, which are worth stating in the report:
- **A flood of perfectly normal-looking SYNs is not flagged** (`craft syn count=40` → all benign). The "many SYNs
  lately" answers only tip the balance together with a flood-like header. A careful attacker who copies a real
  client's options and TTL would get through.
- **Shortcuts learned from synthetic data.** The model relies strongly on the IP "don't fragment" flag: switching it
  off flips some normal frames to malicious, because the synthetic normal TCP traffic always set it.
- **Some odd combinations pass:** e.g. `craft ack flags=SF dport=22` (SYN+FIN) is benign, while `craft syn flags=SF`
  is malicious.

All three point the same way: retrain on real captures (UNSW-NB15 / CIC-IDS2017, see the README). The hardware
doesn't change; only `cfg.txt` / `snn_fw.bin` do.

## 6. How we know the board's answers are real

`sw/cv96/tools/cosim/check_custom.py` (part of `sim/run_all.sh`) runs these custom modes on the FPGA's RTL and
recomputes every verdict independently in Python from the same bytes:

```
craft all (22 presets)                   22 frames,  15 malicious: OK, identical to the golden model
craft synflood (40 packets)              40 frames,  40 malicious: OK, identical to the golden model
craft xmas count=40 (port scan)          40 frames,  40 malicious: OK, identical to the golden model
craft pingflood count=30                 30 frames,  30 malicious: OK, identical to the golden model
craft syn ttl=200 opts=0 win=512          1 frames,   1 malicious: OK, identical to the golden model
craft synflood ttl=64 opts=12 count=5     5 frames,   5 malicious: OK, identical to the golden model
craft ack flags=SF dport=22               1 frames,   0 malicious: OK, identical to the golden model
craft dns dport=0 payload=900             1 frames,   1 malicious: OK, identical to the golden model
frame <hex of test frame 47>              1 frames,   1 malicious: OK, identical to the golden model
pcap: test frames 0-199 (Ethernet)      200 frames, 118 malicious: OK, identical to the golden model
pcap: frames 40-99 (Linux cooked)        60 frames,  41 malicious: OK, identical to the golden model
RESULT: PASS
```

To check a board run yourself, add `hex` and feed the frames to `model/explain_frame.py`. The verdict and both spike
counts must match.
