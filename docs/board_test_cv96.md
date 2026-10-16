# Testing the SNN accelerator on the Chameleon96 board

This explains:
- what feedback to expect from the board;
- how a test program talks to the FPGA through memory addresses;
- what each of the 10 board tests does and why.

The program is `sw/cv96/tools/snn_test.c`. It uses **the same 600 frames, weights and expected answers as the
simulation testbenches** (`sim/vectors/`), built into the binary.

---

## 1. What feedback to expect

| signal | meaning |
|---|---|
| **LED2 blinks**, ~0.67 s on / 0.67 s off | the heartbeat of the SNN block: the new RBF is loaded and the FPGA design is clocked. Nothing else; it blinks even with no traffic |
| **LED1 lights for ~0.17 s** | **one frame was judged malicious.** A burst of malicious frames (e.g. a SYN flood) keeps it lit or flickering. Benign frames never light it |
| **text in the terminal** | the main feedback: every test prints PASS/FAIL, and `demo` mode prints one line per frame with the verdict and the spike counts of both output neurons |

LED1 is the hardware's own reaction (`rtl/snn_lookaside_avmm.v`: `flash` counter, 2²⁴ cycles at 100 MHz). It lights
whenever *any* software (this test program or the kernel module) gets a malicious verdict.

Nothing happens on its own: **the FPGA only classifies what software writes into it.** On this board the network
adapter (USB WiFi) is on the ARM side, so frames reach the FPGA only when a program sends them (this test, or later
the kernel module `snn_fw.ko` for live WiFi traffic).

## 2. How a program talks to the FPGA: memory-mapped registers

The HPS (ARM) sees the FPGA through the **lightweight HPS-to-FPGA bridge** at physical address `0xFF200000`. Platform
Designer placed the SNN accelerator at offset `0x10000`, so its registers start at **`0xFF210000`**. A program maps
that range with `mmap("/dev/mem")` and then simply reads and writes 32-bit words.

| byte address | register | access | meaning |
|---|---|---|---|
| `0xFF210000` | CTRL | R/W | bit 0: interrupt enable |
| `0xFF210004` … `0xFF210010` | TH1, TH2, TIMING, B2 | R/W | thresholds, time steps / leak, output biases |
| `0xFF210040` … `0xFF21007C` | W2[0..15] | R/W | hidden → output weights |
| `0xFF210080` | SUBMITTED | R | frames accepted since power-up |
| `0xFF210084` | REJECTED | R | SUBMITs refused because the accelerator was busy |
| `0xFF210088` | MALICIOUS | R | frames judged malicious |
| `0xFF21008C` | LAST | R | last verdict: [8] mal, [7:4] cnt1, [3:0] cnt0 |
| `0xFF210400` … `0xFF2107FC` | W1 | W | input → hidden weights (write only) |
| **`0xFF211000` … `0xFF21107C`** | **HDR[0..31]** | W | **the frame header window**: 32 words = 128 bytes, little endian (byte 0 of the frame in bits [7:0] of the first word) |
| **`0xFF211080`** | **SUBMIT** | W | **start**: [15:0] true frame length, [23:16] header bytes written (1–128), [31:24] a tag you choose |
| **`0xFF211084`** | **VERDICT** | R | **result** (reading removes it from the queue): [31] valid, [30] malicious, [27:24] cnt1, [23:20] cnt0, [7:0] your tag |
| `0xFF211088` | STATUS | R | [0] ready for a SUBMIT, [1] a verdict is waiting, [12:8] verdicts queued (max 16) |
| `0xFF21108C` | ID | R | always `0x534E4E32` ("SNN2") |

(Byte address = `0xFF210000` + 4 × word address; the word addresses are the ones in `docs/design.md` §3.2.)

### Classifying one frame, step by step

Example: frame 0 of the test vectors, a 98-byte ping (`02 98 ca d7 1a 9d 02 9b 7f c2 df 83 08 00 45 00 …`).

1. Read **STATUS** until bit 0 (ready) is 1.
2. Write the first ≤ 128 header bytes, 4 per word, into **HDR**:
   - `0xFF211000 ← 0xd7ca9802` (bytes 0–3: 02 98 ca d7, little endian);
   - `0xFF211004 ← 0x9b029d1a`;
   - … up to 25 words for 98 bytes.
3. Write **SUBMIT** `0xFF211080 ← 0x00620062 | (tag << 24)`: length 98 = 0x62, 98 header bytes, tag 0.
4. The FPGA streams those bytes through the parser → 64 spikes → SNN. This takes ~30 FPGA clock cycles, about 0.3 µs.
5. Read **VERDICT** `0xFF211084` until bit 31 is 1. For this frame: `0x80400000` = valid, not malicious, cnt0 = 4,
   cnt1 = 0, tag 0. That matches the golden model: `4 0 0` in `expected.txt` line 1.

Only the header (≤ 128 bytes) crosses the bridge. The true length goes in SUBMIT, so length-based features are
still exact, and the results are bit-identical to the in-line version.

You can poke the simple registers by hand with BusyBox `devmem`, if the image has it:
```sh
devmem 0xFF21108C 32     # ID     -> 0x534E4E32
devmem 0xFF211088 32     # STATUS -> 0x00000001 (ready, nothing queued)
devmem 0xFF210080 32     # frames submitted since boot
```
Whole frames are tedious by hand, which is what `snn_test` is for.

---

## 3. Running the board test

Short copy-paste version: **`docs/cv96_run_snn_test.md`**.

**On the laptop** (the binary is already built; rebuild with `make -C sw/cv96/tools snn_test`):
```bash
scp sw/cv96/tools/snn_test root@<board-ip>:/root/
```
No WiFi yet? Copy it to the SD card's root filesystem instead, or use any USB stick. It's one 2.9 MB static file.
md5 `3f75f06fa17929ce78364e716637ce92`.

**On the board**, as root:
```sh
cat /sys/class/fpga_manager/fpga0/state          # operating
for b in /sys/class/fpga_bridge/*; do echo "$(cat $b/name) $(cat $b/state)"; done   # lwhps2fpga ... enabled
lsmod | grep snn_fw && rmmod snn_fw              # the kernel module must not be loaded at the same time
cd /root && chmod +x snn_test
./snn_test                                        # all ten tests (a few seconds)
./snn_test demo                                   # watch LED1 during the SYN flood (150 ms per frame)
./snn_test demo 400                               # slower
./snn_test C9                                     # a single test
./snn_test stats                                  # ID, status, counters
```
Do not run it if the bridge reads **disabled**: an access through a disabled bridge can hang the board.

**Expected output.** This is the run against the RTL in co-simulation; the board must print the same, except the
throughput line:
```
SNN accelerator found at 0xff210000 (FPGA via /dev/mem)
[C1] identity and idle state (T1)
    ID 0x534e4e32, STATUS 0x1; since boot: submitted 0, rejected 0, malicious 0
  PASS C1
[C2] load weights, read back (T2)
    276 weight/threshold words written, 20 readable registers checked
  PASS C2
[C3] 600 golden frames, bit-exact (T3)
    600 frames: malicious 197, benign 403 | vs ground truth TP=197 FP=0 TN=402 FN=1
  PASS C3
[C4] hardware counters (T3 counter checks)
    frames 0-99: submitted +100, malicious +41, rejected +0, last verdict 0x180
  PASS C4
[C5] status bits and verdict-ready interrupt flag
    irq_en set/cleared; STATUS goes 'verdict available, 1 queued' -> empty after the read
  PASS C5
[C6] odd sizes: runt, 0/200-byte header, 1518 B (T7)
    8-byte runt (shorter than an Ethernet header)    -> verdict returned (benign)
    SUBMIT with 0 header bytes (treated as 1)        -> verdict returned (benign)
    SUBMIT with 200 header bytes (clipped to 128)    -> verdict returned (benign)
    1518-byte maximum frame, 128-byte header         -> verdict returned (benign)
  PASS C6
[C7] fail-safe with no weights loaded
    output weights = 0 (as after power-up): 101 SYN-flood frames -> 0 flagged (fail-safe: all pass)
  PASS C7
[C8] several frames in flight (T8)
    120 frames, up to 12 in flight before reading verdicts: order and values bit-exact
  PASS C8
[C9] overload: submit without waiting (T9)
    40 SUBMITs without waiting: 16 accepted, 24 rejected (counted), 16 verdicts back in order
  PASS C9
[C10] recovery after overload (T10)
    after the overload: queue drained, window flushed, frames 0-59 bit-exact again
  PASS C10

throughput (C3): ... frames/s, ... us per frame incl. bus transfers
============================================================
 RESULT: PASS (10 of 10 tests passed)
============================================================
```
- **C1 counters:** on the board they show whatever ran since boot, not necessarily 0.
- **C9 split:** the exact accepted/rejected split depends on how fast the ARM writes. Only the rules are checked.
- **Throughput:** on the board it is limited by ARM register writes over the bridge, so expect tens of µs per frame.
  The FPGA itself needs ~0.3 µs.

---

## Result on the real board (2026-10-16): PASS

Run on the Chameleon96 with `cv96_snn.rbf`, as root:

```
[C3] 600 golden frames, bit-exact (T3)
    600 frames: malicious 197, benign 403 | vs ground truth TP=197 FP=0 TN=402 FN=1
  PASS C3
[C9] overload: submit without waiting (T9)
    40 SUBMITs without waiting: 22 accepted, 18 rejected (counted), 22 verdicts back in order
  PASS C9
throughput (C3): 108989 frames/s, 9.2 us per frame incl. bus transfers
 RESULT: PASS (10 of 10 tests passed)
```

- **Every test passes.** The FPGA silicon gives the same answer as the Python model and the RTL simulations for all
  600 frames, including both neurons' spike counts.
- **C9:** 22 accepted / 18 rejected on the board, vs 16 / 24 in co-simulation. The ARM writes more slowly than the
  simulated bus, so the accelerator finishes a few frames while the 40 requests are still arriving. Only the rules are
  checked (accepted + rejected = 40, every accepted frame answered, in order).
- **Throughput:** 109,000 frames/s (9.2 µs per frame), limited by the CPU's register writes over the lightweight
  bridge. The FPGA work itself is ≈ 0.3 µs.
- **Counters before the run** (`submitted 1536, rejected 36, malicious 445`) come from earlier runs since boot. Each
  test checks only the change it caused.

## 4. The ten tests and how they match the simulation testbench

The simulation suite T1–T10 (`sim/asic/tb_snn_asic.sv`, `docs/functional_verification.md`) tests the **in-line**
filter. The Chameleon96 carries the **look-aside** version of the same classifier, so each board test is the
look-aside equivalent.

| board test | testbench | what it does | what PASS proves | what a FAIL usually means |
|---|---|---|---|---|
| **C1** identity and idle state | T1 reset values | reads ID; drains stale verdicts; checks STATUS = ready with nothing queued; prints counters | the FPGA image is ours, the bridge works, the block is idle | wrong RBF, bridge disabled, or the kernel module is also using it |
| **C2** load weights, read back | T2 config | writes all 276 weight/threshold words (the same `cfg.txt`) and reads back the 20 readable ones (W1 is write-only) | the CPU can install and check a trained network | bridge write problems; wrong address offset |
| **C3** 600 golden frames | T3 golden run | first sends 32 neutral ARP frames to empty the 32-frame SYN/ping rate window (it keeps state between runs), then classifies all 600 test frames one by one and compares **every verdict and both spike counts** with the golden model | the FPGA silicon gives bit-identical answers to the Python model and to every simulation. Detection: 197 of 198 attacks, 0 false alarms | any mismatch = hardware/RTL difference. Send me the `[ERR]` lines |
| **C4** hardware counters | T3 counter checks | replays frames 0–99 and checks the counters increase by exactly +100 submitted, +41 malicious, +0 rejected, and that LAST = the golden last verdict | the counters that the kernel module reports are trustworthy | counter wiring, or another program submitting at the same time |
| **C5** status + interrupt flag | (look-aside specific) | turns the interrupt enable on, submits one frame, checks STATUS shows "verdict waiting, 1 queued", reads it, checks the queue is empty and that an empty read is not valid | the handshake a driver relies on: no lost or phantom verdicts | the read-to-pop logic misbehaves |
| **C6** odd sizes | T7 size limits | an 8-byte runt, SUBMIT claiming 0 header bytes (hardware uses 1), SUBMIT claiming 200 (hardware clips to 128), a 1518-byte maximum frame | malformed requests from a buggy driver can't hang the accelerator: every request gets exactly one verdict with the right tag | the sequencer hangs or produces extra or missing verdicts |
| **C7** fail-safe without weights | "after reset, before weights" (design summary) | sets the output weights to 0, as after power-up, and sends 101 SYN-flood frames | with no network loaded, **nothing** is flagged (fail-open), so a board that boots without weights doesn't block traffic | weights not cleared, or a stuck output |
| **C8** several frames in flight | T8 back-to-back | submits each next frame as soon as the accelerator is ready, reads 12 verdicts at a time; 120 frames | pipelining and the 16-entry verdict queue keep order and values exact | ordering bug in the queue |
| **C9** overload | T9 overload | fires 40 SUBMITs without waiting and without reading | extra requests are **refused and counted** (REJECTED), never corrupting accepted ones; accepted + rejected = 40, and every accepted frame returns a verdict in order | lost or duplicated verdicts under pressure |
| **C10** recovery | T10 reset recovery | drains the queue, reloads the weights, flushes the window, replays frames 0–59 | after an overload the accelerator is fully usable again without a reboot | state left over from the overload |

Testbench cases with no board equivalent:
- **T4 / T5 (monitor mode, bypass):** in the look-aside design that policy lives in the kernel module
  (`echo "drop 0|1" > /proc/snn_fw`), not in the FPGA.
- **T6 (bad-FCS frames):** the WiFi driver discards those before Linux sees them.

### What the 600 test frames contain

Same files as the simulation (details in `docs/explained_simply.md` §5):

| frames | traffic |
|---|---|
| 0–46 | normal: web sessions, DNS, pings |
| 47–247 | **SYN flood** (153 attack frames mixed with normal traffic) |
| 260–276 | **port-0 probes** |
| 341–589 | **ACK scan** (41 probes inside lots of normal traffic) |
| the rest | normal |

Correct result: 197 flagged. The one miss, frame 128, is also missed by the golden model.

### Demo mode

`./snn_test demo` loads the weights, empties the rate window, and replays frames 0–140 slowly:
```
frame  45  benign      -> benign     (benign neuron  8 spikes, malicious neuron  0)
frame  46  benign      -> benign     (benign neuron  4 spikes, malicious neuron  0)
frame  47  syn_flood   -> MALICIOUS  (benign neuron  0 spikes, malicious neuron  7)
frame  48  syn_flood   -> MALICIOUS  (benign neuron  0 spikes, malicious neuron  8)
...
```
LED1 stays dark during frames 0–46, then flashes with almost every line once the flood starts at frame 47. That's
the visible proof for an audience. A line marked `<-- differs from golden model!` would mean a hardware problem.

---

## 5. How this program was verified before reaching the board

`sw/cv96/tools/cosim/run_cosim.sh` builds the **same `snn_test.c`** against the accelerator RTL compiled with
Verilator. There, `hw_rd` / `hw_wr` perform real Avalon bus cycles (read latency 1, like the bridge) instead of
`/dev/mem` accesses. All 10 tests pass there. A deliberately corrupted golden answer was reported as `[ERR] … FAIL`,
so the checks are real. On the board, only the 15-line `/dev/mem` back end (`hw_devmem.c`) is new.

```bash
sw/cv96/tools/cosim/run_cosim.sh          # all tests against the RTL (needs Verilator; ~5 s)
sw/cv96/tools/cosim/run_cosim.sh demo 0   # demo output without delays
```

## 6. Troubleshooting

| symptom | cause / fix |
|---|---|
| `open /dev/mem (run as root)` | log in as root |
| `no SNN accelerator at 0xff210000 (ID reads 0x...)` | the old RBF is loaded, or the bridge is disabled: check the two `cat` commands in §3; reboot with `cv96_snn.rbf` |
| the program hangs at the first access | the lwhps2fpga bridge is disabled: enable it in U-Boot (`bridge enable`) or via `/sys/class/fpga_bridge`, then reboot |
| `snn_fw.ko is loaded …` | `rmmod snn_fw` first; run the module afterwards for live WiFi traffic (`docs/chameleon96_deploy.md`) |
| C3 mismatches on a few early frames only | something else submitted frames between the window flush and the replay; make sure nothing else uses the accelerator |
| LED1 never lights in `demo` | check `snn_test stats` (MALICIOUS must rise); if it rises, LED1 is being overridden by the Linux LED PIO (`led_pio[0]` is OR-ed in: make sure it is 0) |

## 7. After this: live traffic

When `snn_test` passes:
1. `insmod snn_fw.ko iface=wlan0 drop=0` to classify every received WiFi frame in the kernel.
2. Attack the board from the laptop.
3. Watch LED1 and `/proc/snn_fw`.

See `docs/chameleon96_deploy.md` and `docs/verification_guide.md` §D.
