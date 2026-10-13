# Chameleon96 on-board WiFi/BT: findings and fix plan

## Findings (from the schematic and the stock Novtech design)

* **Module:** `TiWi-L-WB` with Broadcom-style nets (`WL_REG_ON`, `BT_REG_ON`, 32 kHz
  LPO oscillator, `BT_HOST_WAKE`). This matches the `CONFIG_BRCMFMAC_SDIO=y` in
  `meta-local/.../wifi.cfg`, which expects firmware `brcmfmac43430-sdio.*`.
* **The SDIO bus goes to FPGA fabric pins, not HPS pins** (1.8 V bank):

  | signal | FPGA pin |
  |---|---|
  | SD_CLK | AB20 |
  | SD_CMD | AB18 |
  | SD_D0 / D1 / D2 / D3 | Y14 / AB19 / AA18 / AB15 |
  | BT UART RXD / TXD / CTS / RTS | AB14 / AA15 / AB17 / AA16 (stock design → HPS UART1 via FPGA) |
  | BT_HOST_WAKE | AB12 |

* The Cyclone V HPS has **one** SD/MMC controller, and it boots the microSD. So
  the stock design (`/media/additional_space/Chameleon96/CV_96_SD_RF`) puts a
  soft host in the FPGA: **SLS `sls_sdhc`** (Platform Designer component
  `sd_host_controller` 1.14, with Avalon DMA masters and an IRQ).
  * The IP RTL is **Quartus-encrypted** (`sls_sdhc_top.v`), so its internal
    clocking can't be fixed or even inspected.
  * Its Linux driver is **out of tree** (DT `compatible = "SLS,sls_sdio-1.10",
    "sls,sdio-cntrlr"`, `bus-width = <1>`), written for the Novtech 4.x
    kernel. It isn't in 6.18, so the stock HDL can't work with your kernel even
    with perfect clocking.
  * The stock top drives `SD_CLK` straight from fabric logic
    (`FPGA_1V8_WIFI_SD_CLK <= sd_host_controller_CLK_o`): no DDIO output
    register and no output timing constraints. Plausibly that's the "clock
    issue" you saw.

## Options

1. **Open SDIO host with a mainline driver (recommended).** Use LiteX
   **LiteSDCard** with the in-tree `litex_mmc` driver (`CONFIG_MMC_LITEX`,
   mainline since 5.18). Generate the core standalone, bridge its Wishbone CSR
   to the LW H2F bridge and its DMA to the F2H/F2SDRAM bridge. Drive SD_CLK
   through an `altddio_out` with proper SDC. For `brcmfmac`, SDIO in-band IRQ
   support in `litex_mmc` is limited, so the MMC core falls back to polling.
   That works, just more slowly. Effort: several days. Risk: CMD53 byte-mode
   corner cases.
2. **Revive the SLS core.** Recover the SLS driver source from the Novtech VM
   (needs root:
   `sudo guestmount -a NovTech_VM_U14.04.4.vmdk -i --ro /mnt/nv && grep -rl "sls,sdio-cntrlr" /mnt/nv/home`),
   port it to 6.18, and fix only what's outside the encrypted core (DDIO clock
   output, I/O timing constraints, 50 MHz core clock). Still a black box,
   limited to 1-bit mode.
3. **Keep the USB adapter.** Zero risk, and it's what the SNN demo already uses.

The SNN work doesn't depend on any of these. Tell me if you want option 1
started; I can't test it without the board in the loop.
