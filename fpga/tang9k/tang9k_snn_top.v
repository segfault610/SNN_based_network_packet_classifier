// Tang Nano 9K (GW1NR-LV9QN88PC6/I5) stand-alone IN-LINE SNN firewall demo.
//
//   PC --USB-UART--> SLIP decoder --AXIS--> snn_pkt_filter --AXIS--> SLIP encoder --USB-UART--> PC
//
// The full in-line datapath (store-and-forward buffer, parser, encoder, SNN,
// drop/forward) runs exactly as it would inside a NIC; the UART only replaces
// the PHY/MAC. Host tool: sw/tang9k/tang_demo.py
//
// SLIP-framed messages (END=C0, ESC=DB, ESC_END=DC, ESC_ESC=DD):
//   host -> FPGA  'P' frame...         ingress Ethernet frame
//                 'C' a1 a0 d3 d2 d1 d0  config write (word addr, data; big endian)
//                 'R' a1 a0              config read
//   FPGA -> host  'F' frame...         frame forwarded by the firewall
//                 'V' v                verdict per frame: v[7]=malicious
//                 'r' d3 d2 d1 d0      config read data
// Board: Tang Nano 9K on a custom perfboard with an external FTDI USB-UART header (pins 31/32)
// and 8 external LEDs (tang9k.cst):
//   leds_ext 0 malicious frame (flash)   4 UART RX activity
//            1 heartbeat (~1.2 s)        5 config written
//            2 frame forwarded           6 UART TX activity
//            3 frame blocked             7 under attack: >= 4 of the last 8 verdicts malicious
// LED_ACTIVE_HIGH = 1: pin -> resistor -> LED -> GND. Set 0 for LEDs wired to 3.3 V.
module tang9k_snn_top #(
    parameter CLKS_PER_BIT    = 27,       // 27 MHz / 1 Mbaud
    parameter LED_ACTIVE_HIGH = 1
)(
    input  wire       clk,                // 27 MHz crystal, pin 52
    input  wire       rst_n,              // reset button, pin 3 (active low)
    input  wire       uart_rx,            // pin 31 <- FTDI TX
    output wire       uart_tx,            // pin 32 -> FTDI RX
    output wire [7:0] leds_ext            // external LEDs, pins 75 74 73 72 71 70 51 53
);
    // ------------------------------------------------------------ reset
    reg [3:0] rst_sr = 4'hF;
    always @(posedge clk) rst_sr <= {rst_sr[2:0], !rst_n};
    wire rst = |rst_sr;

    // ------------------------------------------------------------ UART RX + SLIP decode
    wire [7:0] rx_b;
    wire       rx_v;
    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (.clk(clk), .rst(rst), .rx(uart_rx), .data(rx_b), .valid(rx_v));

    reg        esc;
    reg [7:0]  mtype;
    reg [3:0]  midx;                     // byte index within message (saturating)
    reg [7:0]  held;                     // 1-byte delay so the last frame byte gets tlast
    reg        held_v;
    reg [47:0] cmd;                      // collected C/R payload

    reg [7:0]  s_tdata;
    reg        s_tvalid, s_tlast;
    reg        cfg_wr, cfg_rd;
    reg [9:0]  cfg_addr;
    reg [31:0] cfg_wdata;
    wire [31:0] cfg_rdata;
    reg        rd_pend;                  // read response due next cycle

    wire       is_end = rx_v && !esc && rx_b == 8'hC0;
    wire       is_esc = rx_v && !esc && rx_b == 8'hDB;
    wire [7:0] dbyte  = !esc ? rx_b : (rx_b == 8'hDC) ? 8'hC0 : (rx_b == 8'hDD) ? 8'hDB : rx_b;
    wire       dvalid = rx_v && !is_end && !is_esc;

    always @(posedge clk) begin
        if (rst) begin
            esc <= 1'b0; mtype <= 8'd0; midx <= 4'd0; held_v <= 1'b0; held <= 8'd0; cmd <= 48'd0;
            s_tvalid <= 1'b0; s_tlast <= 1'b0; s_tdata <= 8'd0;
            cfg_wr <= 1'b0; cfg_rd <= 1'b0; cfg_addr <= 10'd0; cfg_wdata <= 32'd0; rd_pend <= 1'b0;
        end else begin
            s_tvalid <= 1'b0; s_tlast <= 1'b0;
            cfg_wr   <= 1'b0; cfg_rd  <= 1'b0;
            rd_pend  <= cfg_rd;
            if (rx_v) esc <= is_esc;
            if (dvalid) begin
                if (midx == 4'd0) mtype <= dbyte;
                else if (mtype == "P") begin
                    if (held_v) begin s_tvalid <= 1'b1; s_tdata <= held; end
                    held <= dbyte; held_v <= 1'b1;
                end else
                    cmd <= {cmd[39:0], dbyte};
                if (midx != 4'hF) midx <= midx + 1'b1;
            end
            if (is_end) begin
                midx <= 4'd0;
                if (mtype == "P" && held_v) begin
                    s_tvalid <= 1'b1; s_tdata <= held; s_tlast <= 1'b1;
                end
                if (mtype == "C" && midx == 4'd7) begin
                    cfg_wr <= 1'b1; cfg_addr <= cmd[41:32]; cfg_wdata <= cmd[31:0];
                end
                if (mtype == "R" && midx == 4'd3) begin
                    cfg_rd <= 1'b1; cfg_addr <= cmd[9:0];
                end
                held_v <= 1'b0;
                mtype  <= 8'd0;
            end
        end
    end

    // ------------------------------------------------------------ firewall (in-line)
    wire [7:0] m_tdata;
    wire       m_tvalid, m_tlast, m_tready;
    wire       v_valid, v_mal;

    snn_pkt_filter #(.BUF_AW(12)) u_fw (
        .clk(clk), .rst(rst),
        .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid), .s_axis_tready(),
        .s_axis_tlast(s_tlast), .s_axis_tuser(1'b0),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
        .m_axis_tlast(m_tlast), .m_axis_tuser(),
        .cfg_wr(cfg_wr), .cfg_rd(cfg_rd), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata), .cfg_rdata(cfg_rdata),
        .verdict_valid(v_valid), .verdict_mal(v_mal)
    );

    // verdict events and read data are queued; frames have lowest priority.
    // 64 entries: a 1500-byte forwarded frame takes as long to send as ~25 minimum
    // frames take to arrive, so verdicts must queue behind it.
    wire [7:0] vq_d;
    wire       vq_empty;
    reg        vq_pop;
    sync_fifo #(.W(8), .DEPTH(64)) u_vq (.clk(clk), .rst(rst), .wr_en(v_valid), .wr_data({v_mal, 7'd0}),
        .rd_en(vq_pop), .rd_data(vq_d), .empty(vq_empty), .full(), .count());
    reg        rr_v;
    reg [31:0] rr_d;
    reg        rr_clr;
    always @(posedge clk) begin
        if (rst) rr_v <= 1'b0;
        else if (rd_pend) begin rr_v <= 1'b1; rr_d <= cfg_rdata; end
        else if (rr_clr) rr_v <= 1'b0;
    end

    // ------------------------------------------------------------ SLIP encode + UART TX
    // message = type byte, payload (escaped), END
    localparam T_IDLE = 3'd0, T_TYPE = 3'd1, T_BODY = 3'd2, T_ESC2 = 3'd3, T_END = 3'd4;
    reg  [2:0]  ts;
    reg  [7:0]  tmsg;                    // 'F', 'V', 'r'
    reg  [2:0]  tcnt;
    reg  [31:0] tsh;
    reg  [7:0]  tesc2;
    reg         tlast_seen;
    reg  [7:0]  tx_d;
    reg         tx_v;
    wire        tx_rdy;
    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (.clk(clk), .rst(rst), .data(tx_d), .valid(tx_v), .ready(tx_rdy), .tx(uart_tx));

    // payload byte source for the current message
    wire       f_has  = m_tvalid;
    wire [7:0] body_b = (tmsg == "F") ? m_tdata : tsh[31:24];
    wire       body_v = (tmsg == "F") ? m_tvalid : (tcnt != 0);
    assign m_tready   = (ts == T_BODY) && (tmsg == "F") && !tlast_seen && tx_rdy && !tx_v && m_tvalid;

    always @(posedge clk) begin
        vq_pop <= 1'b0;
        rr_clr <= 1'b0;
        tx_v   <= 1'b0;
        if (rst) begin
            ts <= T_IDLE; tmsg <= 8'd0; tcnt <= 3'd0; tsh <= 32'd0; tlast_seen <= 1'b0;
        end else if (tx_rdy && !tx_v) begin
            case (ts)
                T_IDLE: begin
                    if (rr_v)               begin tmsg <= "r"; tsh <= rr_d; tcnt <= 3'd4; rr_clr <= 1'b1; ts <= T_TYPE; end
                    else if (!vq_empty)     begin tmsg <= "V"; tsh <= {vq_d, 24'd0}; tcnt <= 3'd1; vq_pop <= 1'b1; ts <= T_TYPE; end
                    else if (f_has)         begin tmsg <= "F"; tcnt <= 3'd0; tlast_seen <= 1'b0; ts <= T_TYPE; end
                end
                T_TYPE: begin tx_d <= tmsg; tx_v <= 1'b1; ts <= T_BODY; end
                T_BODY: begin
                    if ((tmsg == "F" && tlast_seen) || (tmsg != "F" && tcnt == 0)) begin
                        ts <= T_END;
                    end else if (body_v) begin
                        if (tmsg == "F") tlast_seen <= m_tlast;
                        else begin tsh <= tsh << 8; tcnt <= tcnt - 1'b1; end
                        if (body_b == 8'hC0)      begin tx_d <= 8'hDB; tesc2 <= 8'hDC; ts <= T_ESC2; end
                        else if (body_b == 8'hDB) begin tx_d <= 8'hDB; tesc2 <= 8'hDD; ts <= T_ESC2; end
                        else                       tx_d <= body_b;
                        tx_v <= 1'b1;
                    end
                end
                T_ESC2: begin tx_d <= tesc2; tx_v <= 1'b1; ts <= T_BODY; end
                T_END:  begin tx_d <= 8'hC0; tx_v <= 1'b1; ts <= T_IDLE; end
                default: ts <= T_IDLE;
            endcase
        end
    end

    // ------------------------------------------------------------ LEDs
    reg [21:0] f_mal, f_pass, f_blk, f_rx, f_tx, f_cfg;
    reg [24:0] hb;
    reg [7:0]  hist;                      // last 8 verdicts, 1 = malicious
    always @(posedge clk) begin
        if (rst) begin
            f_mal <= 0; f_pass <= 0; f_blk <= 0; f_rx <= 0; f_tx <= 0; f_cfg <= 0; hb <= 0; hist <= 0;
        end else begin
            hb    <= hb + 1'b1;
            f_mal <= (v_valid && v_mal)          ? 22'h3FFFFF : (f_mal  != 0 ? f_mal  - 1'b1 : 0);
            f_blk <= (v_valid && v_mal)          ? 22'h3FFFFF : (f_blk  != 0 ? f_blk  - 1'b1 : 0);
            f_pass<= (m_tvalid && m_tready && m_tlast) ? 22'h3FFFFF : (f_pass != 0 ? f_pass - 1'b1 : 0);
            f_rx  <= rx_v                        ? 22'h0FFFFF : (f_rx   != 0 ? f_rx   - 1'b1 : 0);
            f_tx  <= tx_v                        ? 22'h0FFFFF : (f_tx   != 0 ? f_tx   - 1'b1 : 0);
            f_cfg <= cfg_wr                      ? 22'h0FFFFF : (f_cfg  != 0 ? f_cfg  - 1'b1 : 0);
            if (v_valid) hist <= {hist[6:0], v_mal};
        end
    end
    wire [3:0] n_mal = hist[0] + hist[1] + hist[2] + hist[3] + hist[4] + hist[5] + hist[6] + hist[7];
    wire [7:0] led_on = {n_mal >= 4'd4, f_tx != 0, f_cfg != 0, f_rx != 0,
                         f_blk != 0, f_pass != 0, hb[24], f_mal != 0};
    assign leds_ext = LED_ACTIVE_HIGH ? led_on : ~led_on;

endmodule
