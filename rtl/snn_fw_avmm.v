// snn_fw_avmm
// Avalon-MM slave wrapper around snn_pkt_filter for SoC-FPGA bring-up
// (Chameleon96: HPS lightweight H2F bridge -> this slave). The board has no
// FPGA-side Ethernet PHY, so Linux injects frames byte-wise and reads back the
// frames that the firewall forwarded. The same register map loads the weights.
//
// Word address map (32-bit, readLatency = 1, no waitrequest):
//   0x000-0x3FF  snn_pkt_filter config/status space (see snn_pkt_filter.v)
//   0x400  TX_BYTE  W: [7:0] byte, [8] last  -> one ingress beat
//   0x401  TX_WORD  W: 4 bytes little-endian, never last (bulk payload)
//   0x402  RX_POP   R: [7:0] byte, [8] last, [9] valid  (pops one egress byte)
//   0x403  RX_LEVEL R: bytes waiting in egress FIFO
//   0x404  ID       R: 0x534E_4E31 ("SNN1")
module snn_fw_avmm #(
    parameter BUF_AW   = 12,
    parameter RXF_AW   = 11,              // egress capture FIFO (2 KiB)
    parameter W1_INIT  = ""
)(
    input  wire        clk,
    input  wire        reset,

    input  wire [10:0] avs_address,
    input  wire        avs_write,
    input  wire [31:0] avs_writedata,
    input  wire        avs_read,
    output reg  [31:0] avs_readdata,
    output wire        avs_waitrequest,

    output wire [1:0]  leds              // [0] malicious-frame flash, [1] heartbeat
);

    // ------------------------------------------------------------ ingress
    reg  [7:0] in_data;
    reg        in_valid, in_last;
    reg  [1:0] word_left;
    reg [23:0] word_rest;

    always @(posedge clk) begin
        if (reset) begin
            in_valid  <= 1'b0;
            in_last   <= 1'b0;
            in_data   <= 8'd0;
            word_left <= 2'd0;
            word_rest <= 24'd0;
        end else begin
            in_valid <= 1'b0;
            in_last  <= 1'b0;
            if (word_left != 2'd0) begin           // drain rest of a TX_WORD
                in_valid  <= 1'b1;
                in_data   <= word_rest[7:0];
                word_rest <= word_rest >> 8;
                word_left <= word_left - 2'd1;
            end else if (avs_write && avs_address == 11'h400) begin   // (word_left==0 here)
                in_valid <= 1'b1;
                in_data  <= avs_writedata[7:0];
                in_last  <= avs_writedata[8];
            end else if (avs_write && avs_address == 11'h401) begin
                in_valid  <= 1'b1;
                in_data   <= avs_writedata[7:0];
                word_rest <= avs_writedata[31:8];
                word_left <= 2'd3;
            end
        end
    end

    // stall a TX write while the previous TX_WORD is still being serialised
    assign avs_waitrequest = avs_write && (word_left != 2'd0);

    // ------------------------------------------------------------ firewall
    wire        cfg_sel = (avs_address[10] == 1'b0);
    wire [31:0] cfg_rdata;
    wire [7:0]  m_tdata;
    wire        m_tvalid, m_tlast, m_tready;
    wire        v_valid, v_mal;

    snn_pkt_filter #(.BUF_AW(BUF_AW), .W1_INIT(W1_INIT)) u_fw (
        .clk(clk), .rst(reset),
        .s_axis_tdata(in_data), .s_axis_tvalid(in_valid), .s_axis_tready(),
        .s_axis_tlast(in_last), .s_axis_tuser(1'b0),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
        .m_axis_tlast(m_tlast), .m_axis_tuser(),
        .cfg_wr(avs_write && cfg_sel), .cfg_rd(avs_read && cfg_sel),
        .cfg_addr(avs_address[9:0]), .cfg_wdata(avs_writedata), .cfg_rdata(cfg_rdata),
        .verdict_valid(v_valid), .verdict_mal(v_mal)
    );

    // ------------------------------------------------------------ egress capture
    reg  [8:0]      rxf [0:(1<<RXF_AW)-1];
    reg  [RXF_AW:0] rxf_wp, rxf_rp;
    wire [RXF_AW:0] rxf_lvl  = rxf_wp - rxf_rp;
    wire            rxf_full = rxf_lvl[RXF_AW];
    assign m_tready = !rxf_full;

    reg  [8:0] rxf_q;
    wire       rx_pop = avs_read && (avs_address == 11'h402) && (rxf_lvl != 0);

    always @(posedge clk) begin
        if (m_tvalid && m_tready)
            rxf[rxf_wp[RXF_AW-1:0]] <= {m_tlast, m_tdata};
        rxf_q <= rxf[rxf_rp[RXF_AW-1:0]];
    end

    always @(posedge clk) begin
        if (reset) begin
            rxf_wp <= 0;
            rxf_rp <= 0;
        end else begin
            if (m_tvalid && m_tready) rxf_wp <= rxf_wp + 1'b1;
            if (rx_pop)               rxf_rp <= rxf_rp + 1'b1;
        end
    end

    // ------------------------------------------------------------ read mux
    reg [10:0] rd_addr_q;
    reg        rd_q, pop_q;
    always @(posedge clk) begin
        rd_addr_q <= avs_address;
        rd_q      <= avs_read;
        pop_q     <= rx_pop;
    end
    always @(*) begin
        case (rd_addr_q)
            11'h402: avs_readdata = {22'd0, pop_q, pop_q ? rxf_q : 9'd0};
            11'h403: avs_readdata = {{(31-RXF_AW){1'b0}}, rxf_lvl};
            11'h404: avs_readdata = 32'h534E_4E31;
            default: avs_readdata = rd_addr_q[10] ? 32'd0 : cfg_rdata;
        endcase
    end

    // ------------------------------------------------------------ LEDs
    reg [23:0] flash;
    reg [26:0] hb;
    always @(posedge clk) begin
        if (reset) begin
            flash <= 24'd0;
            hb    <= 27'd0;
        end else begin
            hb <= hb + 1'b1;
            if (v_valid && v_mal) flash <= 24'hFF_FFFF;
            else if (flash != 0)  flash <= flash - 1'b1;
        end
    end
    assign leds = {hb[26], flash != 0};

endmodule
