// snn_lookaside_avmm
// Look-aside SNN packet classifier for an SoC (Chameleon96: HPS + USB WiFi).
// The NIC lives on the HPS side, so the kernel hook (sw/kmod/snn_fw.c) copies
// the first <=128 bytes of every received frame into the header window,
// writes SUBMIT {tag, nbytes, real frame length} and reads the verdict back.
// Only headers cross the bridge; the real length restores length features, so
// verdicts are bit-identical to the in-line filter / golden model.
//
// Avalon-MM slave, 32-bit, word addressed, readLatency = 1, no waitrequest.
//   0x000-0x3FF classifier config (snn_classifier.v), plus
//     0x000 CTRL  [0] irq_en
//     0x020 frames submitted   0x021 submits rejected (not ready)
//     0x022 frames malicious   0x023 last verdict
//   0x400-0x41F HDR[i]   W  header bytes 4i..4i+3 (little endian: byte 4i in [7:0])
//   0x420 SUBMIT         W  [15:0] frame length, [23:16] header bytes (1..128), [31:24] tag
//   0x421 VERDICT        R  pops: [31] valid [30] mal [27:24] cnt1 [23:20] cnt0 [7:0] tag
//   0x422 STATUS         R  [0] ready for SUBMIT  [1] verdict available  [12:8] verdicts queued
//   0x423 ID             R  0x534E_4E32 ("SNN2")
module snn_lookaside_avmm #(
    parameter N_HID = 16
)(
    input  wire        clk,
    input  wire        reset,

    input  wire [10:0] avs_address,
    input  wire        avs_write,
    input  wire [31:0] avs_writedata,
    input  wire        avs_read,
    output reg  [31:0] avs_readdata,

    output wire        irq,               // level: verdict available (if irq_en)
    output wire [1:0]  leds               // [0] malicious-frame flash, [1] heartbeat
);

    // ------------------------------------------------------------ header window
    reg  [31:0] hdr [0:31];
    reg  [31:0] hdr_q;
    reg  [4:0]  hdr_ra;
    always @(posedge clk) begin
        if (avs_write && avs_address[10:5] == 6'b100000)          // 0x400-0x41F
            hdr[avs_address[4:0]] <= avs_writedata;
        hdr_q <= hdr[hdr_ra];
    end

    // ------------------------------------------------------------ sequencer
    wire        can_commit;
    reg         busy;
    reg  [7:0]  nbytes, idx;
    reg  [15:0] flen;
    reg  [7:0]  tag;
    reg         b_vld, b_last;           // beat pipeline (1 cycle behind hdr_ra)
    reg  [1:0]  b_sel;
    wire        ready = !busy && can_commit;
    wire        submit = avs_write && (avs_address == 11'h420);
    wire [7:0]  sub_n  = (avs_writedata[23:16] == 8'd0) ? 8'd1 :
                         (avs_writedata[23:16] > 8'd128) ? 8'd128 : avs_writedata[23:16];

    reg  [31:0] st_sub, st_rej, st_mal;
    reg  [8:0]  st_last;
    reg         irq_en;

    always @(posedge clk) begin
        if (reset) begin
            busy   <= 1'b0;
            idx    <= 8'd0;
            nbytes <= 8'd0;
            flen   <= 16'd0;
            tag    <= 8'd0;
            hdr_ra <= 5'd0;
            b_vld  <= 1'b0;
            b_last <= 1'b0;
            b_sel  <= 2'd0;
            st_sub <= 32'd0;
            st_rej <= 32'd0;
        end else begin
            b_vld <= 1'b0;
            if (submit) begin
                if (ready) begin
                    busy   <= 1'b1;
                    idx    <= 8'd0;
                    nbytes <= sub_n;
                    flen   <= avs_writedata[15:0];
                    tag    <= avs_writedata[31:24];
                    st_sub <= st_sub + 1'b1;
                end else begin
                    st_rej <= st_rej + 1'b1;
                end
            end
            if (busy) begin
                hdr_ra <= idx[6:2];
                b_sel  <= idx[1:0];
                b_vld  <= 1'b1;
                b_last <= (idx == nbytes - 8'd1);
                idx    <= idx + 8'd1;
                if (idx == nbytes - 8'd1)
                    busy <= 1'b0;
            end
        end
    end

    // hdr_ra registered at cycle n -> hdr_q valid at n+2; align beat by one more stage
    reg        b_vld2, b_last2;
    reg [1:0]  b_sel2;
    always @(posedge clk) begin
        if (reset) begin
            b_vld2 <= 1'b0; b_last2 <= 1'b0; b_sel2 <= 2'd0;
        end else begin
            b_vld2 <= b_vld; b_last2 <= b_last; b_sel2 <= b_sel;
        end
    end
    wire [7:0] b_data = hdr_q[8*b_sel2 +: 8];

    // ------------------------------------------------------------ classifier
    wire        cfg_sel = (avs_address[10] == 1'b0);
    wire [31:0] cls_rdata;
    wire        v_valid, v_mal;
    wire [3:0]  v_cnt0, v_cnt1;
    wire [7:0]  v_tag;
    wire        vq_full, vq_empty;
    wire [4:0]  vq_count;
    wire [16:0] vq_data;

    snn_classifier #(.N_HID(N_HID), .TAG_W(8)) u_cls (
        .clk(clk), .rst(reset),
        .beat_data(b_data), .beat_valid(b_vld2), .beat_last(b_last2),
        .frm_commit(1'b1), .frm_len_ovr(1'b1), .frm_len(flen), .frm_tag(tag),
        .can_commit(can_commit),
        .v_valid(v_valid), .v_ready(!vq_full), .v_mal(v_mal), .v_cnt0(v_cnt0), .v_cnt1(v_cnt1), .v_tag(v_tag),
        .cfg_wr(avs_write && cfg_sel), .cfg_rd(avs_read && cfg_sel), .cfg_addr(avs_address[9:0]),
        .cfg_wdata(avs_writedata), .cfg_rdata(cls_rdata)
    );

    wire v_push = v_valid && !vq_full;
    wire v_pop  = avs_read && (avs_address == 11'h421) && !vq_empty;

    sync_fifo #(.W(17), .DEPTH(16)) u_vq (
        .clk(clk), .rst(reset),
        .wr_en(v_push), .wr_data({v_mal, v_cnt1, v_cnt0, v_tag}),
        .rd_en(v_pop), .rd_data(vq_data),
        .empty(vq_empty), .full(vq_full), .count(vq_count)
    );

    always @(posedge clk) begin
        if (reset) begin
            st_mal  <= 32'd0;
            st_last <= 9'd0;
            irq_en  <= 1'b0;
        end else begin
            if (v_push) begin
                st_last <= {v_mal, v_cnt1, v_cnt0};
                if (v_mal) st_mal <= st_mal + 1'b1;
            end
            if (avs_write && avs_address == 11'h000)
                irq_en <= avs_writedata[0];
        end
    end
    assign irq = irq_en && !vq_empty;

    // ------------------------------------------------------------ read mux (latency 1)
    reg [10:0] ra;
    reg [31:0] pop_word;
    always @(posedge clk) begin
        ra       <= avs_address;
        pop_word <= v_pop ? {1'b1, vq_data[16], 2'b00, vq_data[15:8], 12'd0, vq_data[7:0]} : 32'd0;
    end
    always @(*) begin
        case (ra)
            11'h000: avs_readdata = {31'd0, irq_en};
            11'h020: avs_readdata = st_sub;
            11'h021: avs_readdata = st_rej;
            11'h022: avs_readdata = st_mal;
            11'h023: avs_readdata = {23'd0, st_last};
            11'h421: avs_readdata = pop_word;
            11'h422: avs_readdata = {19'd0, vq_count, 6'd0, !vq_empty, ready};
            11'h423: avs_readdata = 32'h534E_4E32;
            default: avs_readdata = ra[10] ? 32'd0 : cls_rdata;
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
            if (v_push && v_mal)  flash <= 24'hFF_FFFF;
            else if (flash != 0)  flash <= flash - 1'b1;
        end
    end
    assign leds = {hb[26], flash != 0};

endmodule
