module led_blink_linux (
    // ------------------------------------------------------------
    // FPGA LEDs
    // ------------------------------------------------------------
    output wire FPGA_2V5_RF_LEDS_LED1_PIN_Y19,
    output wire FPGA_2V5_RF_LEDS_LED2_PIN_Y20,

    // ------------------------------------------------------------
    // HPS DDR3
    // ------------------------------------------------------------
    output wire [13:0] HPS_DRAM_MA,
    output wire [2:0]  HPS_DRAM_BA,

    output wire        HPS_DRAM_SDCLK_0_P,
    output wire        HPS_DRAM_SDCLK_0_N,

    output wire        HPS_DRAM_MCKE0,
    output wire        HPS_DRAM_nMCS0,
    output wire        HPS_FDRAM_nRAS,
    output wire        HPS_DRAM_nCAS,
    output wire        HPS_DRAM_nMWE,
    output wire        HPS_DRAm_nRESET,

    inout  wire [15:0] HPS_DRAM_MDQ,
    inout  wire [1:0]  HPS_DRAM_DQS0_P,
    inout  wire [1:0]  HPS_DRAM_DQS0_N,

    output wire        HPS_DRAM_MODT0,
    output wire [1:0]  HPS_DRAM_MDM,

    // ------------------------------------------------------------
    // DDR3 OCT calibration reference resistor input
    // ------------------------------------------------------------
    input wire         HPS_DRAM_RZQ
);

    // ------------------------------------------------------------
    // LED PIO
    // ------------------------------------------------------------
    wire [1:0] led_pio;
    wire [1:0] snn_leds;          // [0] malicious-frame flash, [1] heartbeat

    // LED1: SNN flagged a malicious frame (or Linux PIO), LED2: heartbeat ^ PIO
    assign FPGA_2V5_RF_LEDS_LED1_PIN_Y19 = led_pio[0] | snn_leds[0];
    assign FPGA_2V5_RF_LEDS_LED2_PIN_Y20 = led_pio[1] ^ snn_leds[1];


    // ------------------------------------------------------------
    // Platform Designer system
    // ------------------------------------------------------------
    CV96_QSYS u_cv96_qsys (

        // LED PIO
        .pio_rf_leds_external_connection_export(led_pio),

        // SNN look-aside packet classifier (LW bridge offset 0x10000)
        .snn_leds_export(snn_leds),

        // --------------------------------------------------------
        // HPS DDR3
        // --------------------------------------------------------
        .memory_mem_a        (HPS_DRAM_MA),
        .memory_mem_ba       (HPS_DRAM_BA),

        .memory_mem_ck       (HPS_DRAM_SDCLK_0_P),
        .memory_mem_ck_n     (HPS_DRAM_SDCLK_0_N),

        .memory_mem_cke      (HPS_DRAM_MCKE0),
        .memory_mem_cs_n     (HPS_DRAM_nMCS0),
        .memory_mem_ras_n    (HPS_FDRAM_nRAS),
        .memory_mem_cas_n    (HPS_DRAM_nCAS),
        .memory_mem_we_n     (HPS_DRAM_nMWE),
        .memory_mem_reset_n  (HPS_DRAm_nRESET),

        .memory_mem_dq       (HPS_DRAM_MDQ),
        .memory_mem_dqs      (HPS_DRAM_DQS0_P),
        .memory_mem_dqs_n    (HPS_DRAM_DQS0_N),

        .memory_mem_odt      (HPS_DRAM_MODT0),
        .memory_mem_dm       (HPS_DRAM_MDM),

        // --------------------------------------------------------
        // DDR3 OCT RZQ calibration reference
        // --------------------------------------------------------
        .memory_oct_rzqin    (HPS_DRAM_RZQ)

    );

endmodule
