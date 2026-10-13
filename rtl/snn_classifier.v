// snn_classifier
// Reusable classification engine shared by every deployment variant:
//   * snn_pkt_filter      - in-line store-and-forward firewall (MAC datapath, Tang Nano 9K)
//   * snn_lookaside_avmm  - look-aside accelerator for Linux (Chameleon96 HPS)
//
//   byte stream -> pkt_parser -> spike_encoder -> feature FIFO -> snn_core -> verdict
//
// Frame-level sideband (sampled on the beat with beat_last = 1):
//   frm_commit  : 1 = classify this frame, 0 = ignore it (dropped upstream)
//   frm_len_ovr : 1 = use frm_len as the frame length (look-aside mode, where only
//                 the first bytes of the frame are streamed in), 0 = count beats
//   frm_tag     : opaque tag returned with the verdict
// can_commit tells upstream whether a frame ending now may be committed.
//
// Config/status space (word addresses, shared with the wrappers):
//   0x001 TH1  0x002 TH2  0x003 TIMING [3:0] T [5:4] leak  0x004 B2
//   0x010+h W2[h]   0x100+4*row+lane W1
module snn_classifier #(
    parameter N_HID      = 16,
    parameter FEAT_DEPTH = 4,
    parameter TAG_W      = 13,
    parameter TH1_INIT   = 256,
    parameter TH2_INIT   = 128,
    parameter T_INIT     = 8,
    parameter LEAK_INIT  = 2
)(
    input  wire             clk,
    input  wire             rst,

    input  wire [7:0]       beat_data,
    input  wire             beat_valid,
    input  wire             beat_last,
    input  wire             frm_commit,
    input  wire             frm_len_ovr,
    input  wire [15:0]      frm_len,
    input  wire [TAG_W-1:0] frm_tag,
    output wire             can_commit,

    output wire             v_valid,
    input  wire             v_ready,
    output wire             v_mal,
    output wire [3:0]       v_cnt0,
    output wire [3:0]       v_cnt1,
    output wire [TAG_W-1:0] v_tag,

    input  wire             cfg_wr,
    input  wire             cfg_rd,
    input  wire [9:0]       cfg_addr,
    input  wire [31:0]      cfg_wdata,
    output reg  [31:0]      cfg_rdata
);

    // ============================================================ config regs
    reg [15:0]         th1, th2, b2;
    reg [3:0]          t_steps;
    reg [1:0]          leak;
    reg [N_HID*16-1:0] w2;
    integer h;

    always @(posedge clk) begin
        if (rst) begin
            th1     <= TH1_INIT;
            th2     <= TH2_INIT;
            t_steps <= T_INIT;
            leak    <= LEAK_INIT;
            b2      <= 16'd0;
            w2      <= {(N_HID*16){1'b0}};
        end else if (cfg_wr) begin
            case (cfg_addr)
                10'h001: th1 <= cfg_wdata[15:0];
                10'h002: th2 <= cfg_wdata[15:0];
                10'h003: begin t_steps <= cfg_wdata[3:0]; leak <= cfg_wdata[5:4]; end
                10'h004: b2 <= cfg_wdata[15:0];
                default: ;
            endcase
            for (h = 0; h < N_HID; h = h + 1)
                if (cfg_addr == 10'h010 + h)
                    w2[16*h +: 16] <= cfg_wdata[15:0];
        end
    end

    always @(posedge clk) begin
        if (cfg_rd) begin
            case (cfg_addr)
                10'h001: cfg_rdata <= {16'd0, th1};
                10'h002: cfg_rdata <= {16'd0, th2};
                10'h003: cfg_rdata <= {26'd0, leak, t_steps};
                10'h004: cfg_rdata <= {16'd0, b2};
                default: cfg_rdata <= (cfg_addr[9:4] == 6'h01) ? {16'd0, w2[16*cfg_addr[3:0] +: 16]} : 32'd0;
            endcase
        end
    end

    wire w1_we = cfg_wr && (cfg_addr[9:8] == 2'b01);

    // ============================================================ frame sideband
    wire commit = beat_valid && beat_last && frm_commit && can_commit;
    reg  [3:0]       slots;            // frames reserved in parser/encoder/feature FIFO
    reg              commit_q;
    reg              ovr_q;
    reg  [15:0]      len_q;
    reg  [TAG_W-1:0] tag_q, tag_q2;
    wire             feat_pop;

    assign can_commit = (slots < FEAT_DEPTH);

    always @(posedge clk) begin
        if (rst) begin
            slots    <= 4'd0;
            commit_q <= 1'b0;
            ovr_q    <= 1'b0;
            len_q    <= 16'd0;
            tag_q    <= {TAG_W{1'b0}};
            tag_q2   <= {TAG_W{1'b0}};
        end else begin
            commit_q <= commit;
            if (commit) begin
                ovr_q <= frm_len_ovr;
                len_q <= frm_len;
                tag_q <= frm_tag;
            end
            tag_q2 <= tag_q;
            slots  <= slots + commit - feat_pop;
        end
    end

    // ============================================================ parse + encode
    wire        p_done, p_vlan, p_df, p_mf, p_has_l4;
    wire [15:0] p_flen, p_et, p_tot, p_sport, p_dport, p_win;
    wire [3:0]  p_ihl, p_doff;
    wire [12:0] p_foff;
    wire [7:0]  p_ttl, p_proto, p_tflags;
    wire [31:0] p_src, p_dst;

    pkt_parser u_parser (
        .clk(clk), .rst(rst),
        .beat_data(beat_data), .beat_valid(beat_valid), .beat_last(beat_last),
        .done(p_done), .flen(p_flen), .ethertype(p_et), .vlan(p_vlan),
        .ihl(p_ihl), .tot_len(p_tot), .df(p_df), .mf(p_mf), .foff(p_foff),
        .ttl(p_ttl), .proto(p_proto), .src_ip(p_src), .dst_ip(p_dst),
        .has_l4(p_has_l4), .sport(p_sport), .dport(p_dport), .doff(p_doff),
        .tflags(p_tflags), .win(p_win)
    );

    wire        spk_valid;
    wire [63:0] spikes;

    spike_encoder u_enc (
        .clk(clk), .rst(rst),
        .done(p_done), .commit(commit_q),
        .flen(ovr_q ? len_q : p_flen), .ethertype(p_et), .vlan(p_vlan), .ihl(p_ihl), .tot_len(p_tot),
        .df(p_df), .mf(p_mf), .foff(p_foff), .ttl(p_ttl), .proto(p_proto),
        .src_ip(p_src), .dst_ip(p_dst), .has_l4(p_has_l4), .sport(p_sport),
        .dport(p_dport), .doff(p_doff), .tflags(p_tflags), .win(p_win),
        .spk_valid(spk_valid), .spikes(spikes)
    );

    // ============================================================ SNN
    wire [64+TAG_W-1:0] feat_q;
    wire                feat_empty;
    wire                core_in_ready;

    sync_fifo #(.W(64+TAG_W), .DEPTH(FEAT_DEPTH)) u_feat_fifo (
        .clk(clk), .rst(rst),
        .wr_en(spk_valid), .wr_data({tag_q2, spikes}),
        .rd_en(feat_pop), .rd_data(feat_q),
        .empty(feat_empty), .full(), .count()
    );
    assign feat_pop = !feat_empty && core_in_ready;

    snn_core #(.N_IN(64), .N_HID(N_HID), .TAG_W(TAG_W)) u_core (
        .clk(clk), .rst(rst),
        .th1(th1), .th2(th2), .t_steps(t_steps), .leak(leak), .b2(b2), .w2(w2),
        .w1_we(w1_we), .w1_row(cfg_addr[7:2]), .w1_lane(cfg_addr[1:0]), .w1_wdata(cfg_wdata),
        .in_valid(!feat_empty), .in_ready(core_in_ready),
        .in_spikes(feat_q[63:0]), .in_tag(feat_q[64 +: TAG_W]),
        .out_valid(v_valid), .out_ready(v_ready),
        .out_mal(v_mal), .out_cnt0(v_cnt0), .out_cnt1(v_cnt1), .out_tag(v_tag)
    );

endmodule
