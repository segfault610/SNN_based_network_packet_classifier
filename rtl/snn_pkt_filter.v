// snn_pkt_filter
// In-line, store-and-forward SNN packet firewall for an 8-bit AXI-Stream
// Ethernet datapath (drop-in between a MAC RX port and the host-side FIFO/DMA,
// e.g. verilog-ethernet eth_mac_1g -> rx FIFO).
//
//   s_axis --+--> packet buffer (circular, commit/rollback) ----> egress --> m_axis
//            |                                                     ^
//            +--> pkt_parser -> spike_encoder -> feat FIFO -> snn_core -> verdict FIFO
//
// * Ingress never back-pressures (s_axis_tready = 1) because a MAC cannot be
//   stalled; frames that do not fit (buffer / classifier queue full) or that
//   arrive with tuser=1 (bad FCS) are dropped whole and counted.
// * Each committed frame gets exactly one verdict, in order. Egress waits for
//   the head frame's verdict, then forwards it or silently discards it.
// * Malicious frames never reach the host when CTRL.drop_en = 1.
//
// Config/status bus (32-bit word addressed, synchronous):
//   0x000 CTRL    [0] drop_en (rst 1)  [1] bypass (forward everything)
//   0x001 TH1     [15:0]               0x002 TH2 [15:0]
//   0x003 TIMING  [3:0] t_steps  [5:4] leak
//   0x004 B2      [7:0] b_o0  [15:8] b_o1
//   0x010+h W2[h] [7:0] w(h,o0) [15:8] w(h,o1)
//   0x020 frames committed      0x021 frames dropped at ingress
//   0x022 frames flagged mal    0x023 frames forwarded
//   0x024 frames blocked        0x025 last verdict {cnt1[7:4],cnt0[3:0]} [8] mal
//   0x100+4*row+lane  W1 row `row` (input), neurons 4*lane..4*lane+3 (int8 each)
module snn_pkt_filter #(
    parameter BUF_AW     = 12,          // packet buffer = 2^BUF_AW bytes
    parameter FEAT_DEPTH = 4,
    parameter VERD_DEPTH = 16,
    parameter N_HID      = 16,
    parameter DROP_BAD_FRAME = 1,
    parameter TH1_INIT   = 256,
    parameter TH2_INIT   = 128,
    parameter T_INIT     = 8,
    parameter LEAK_INIT  = 2,
    parameter W1_INIT    = ""
)(
    input  wire        clk,
    input  wire        rst,

    // ingress (from MAC)
    input  wire [7:0]  s_axis_tdata,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,
    input  wire        s_axis_tuser,

    // egress (to host FIFO / DMA)
    output wire [7:0]  m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast,
    output wire        m_axis_tuser,

    // config / status
    input  wire        cfg_wr,
    input  wire        cfg_rd,
    input  wire [9:0]  cfg_addr,
    input  wire [31:0] cfg_wdata,
    output reg  [31:0] cfg_rdata,

    // event outputs
    output reg         verdict_valid,   // pulse per classified frame
    output reg         verdict_mal
);

    localparam LENW = BUF_AW + 1;
    localparam DEPTH = 1 << BUF_AW;

    // ============================================================ control / stats
    reg         drop_en, bypass;
    reg [31:0]  st_in, st_drop_in, st_mal, st_pass, st_block;
    reg [8:0]   st_last;
    reg [31:0]  own_rdata;
    reg         own_sel;
    wire [31:0] cls_rdata;

    always @(posedge clk) begin
        if (rst) begin
            drop_en <= 1'b1;
            bypass  <= 1'b0;
        end else if (cfg_wr && cfg_addr == 10'h000) begin
            drop_en <= cfg_wdata[0];
            bypass  <= cfg_wdata[1];
        end
    end

    always @(posedge clk) begin
        if (cfg_rd) begin
            own_sel <= (cfg_addr == 10'h000) || (cfg_addr[9:3] == 7'h04);   // 0x000, 0x020-0x027
            case (cfg_addr)
                10'h000: own_rdata <= {30'd0, bypass, drop_en};
                10'h020: own_rdata <= st_in;
                10'h021: own_rdata <= st_drop_in;
                10'h022: own_rdata <= st_mal;
                10'h023: own_rdata <= st_pass;
                10'h024: own_rdata <= st_block;
                10'h025: own_rdata <= {23'd0, st_last};
                default: own_rdata <= 32'd0;
            endcase
        end
    end
    always @(*) cfg_rdata = own_sel ? own_rdata : cls_rdata;

    // ============================================================ ingress
    reg [8:0]      buf_mem [0:DEPTH-1];
    reg [BUF_AW:0] wr_ptr, wr_commit, rd_ptr;
    reg            drop_cur;
    reg [LENW-1:0] in_len;

    assign s_axis_tready = 1'b1;

    wire            beat       = s_axis_tvalid;
    wire [BUF_AW:0] buf_used   = wr_ptr - rd_ptr;     // sized: wraps correctly
    wire            buf_full   = buf_used[BUF_AW];
    wire            wr_ok      = beat && !drop_cur && !buf_full;
    wire            bad        = (DROP_BAD_FRAME != 0) && s_axis_tuser;
    wire            can_commit;
    wire            frm_ok     = !drop_cur && !buf_full && !bad;
    wire            commit     = beat && s_axis_tlast && frm_ok && can_commit;

    always @(posedge clk) begin
        if (wr_ok)
            buf_mem[wr_ptr[BUF_AW-1:0]] <= {s_axis_tlast, s_axis_tdata};
    end

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr     <= 0;
            wr_commit  <= 0;
            drop_cur   <= 1'b0;
            in_len     <= 0;
            st_in      <= 32'd0;
            st_drop_in <= 32'd0;
        end else if (beat) begin
            if (s_axis_tlast) begin
                if (commit) begin
                    wr_ptr    <= wr_ptr + 1'b1;
                    wr_commit <= wr_ptr + 1'b1;
                    st_in     <= st_in + 1'b1;
                end else begin
                    wr_ptr     <= wr_commit;          // roll back partial frame
                    st_drop_in <= st_drop_in + 1'b1;
                end
                drop_cur <= 1'b0;
                in_len   <= 0;
            end else begin
                if (wr_ok)
                    wr_ptr <= wr_ptr + 1'b1;
                else
                    drop_cur <= 1'b1;
                in_len <= in_len + 1'b1;
            end
        end
    end

    // ============================================================ classifier
    wire            c_valid, c_mal;
    wire [3:0]      c_cnt0, c_cnt1;
    wire [LENW-1:0] c_tag;
    wire            verd_full;

    snn_classifier #(.N_HID(N_HID), .FEAT_DEPTH(FEAT_DEPTH), .TAG_W(LENW),
                     .TH1_INIT(TH1_INIT), .TH2_INIT(TH2_INIT), .T_INIT(T_INIT), .LEAK_INIT(LEAK_INIT)) u_cls (
        .clk(clk), .rst(rst),
        .beat_data(s_axis_tdata), .beat_valid(beat), .beat_last(s_axis_tlast),
        .frm_commit(frm_ok), .frm_len_ovr(1'b0), .frm_len(16'd0), .frm_tag(in_len + 1'b1),
        .can_commit(can_commit),
        .v_valid(c_valid), .v_ready(!verd_full), .v_mal(c_mal), .v_cnt0(c_cnt0), .v_cnt1(c_cnt1), .v_tag(c_tag),
        .cfg_wr(cfg_wr), .cfg_rd(cfg_rd), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata), .cfg_rdata(cls_rdata)
    );

    wire                verd_push = c_valid && !verd_full;
    wire [LENW+9-1:0]   verd_q;
    wire                verd_empty;
    reg                 verd_pop;

    sync_fifo #(.W(LENW+9), .DEPTH(VERD_DEPTH)) u_verd_fifo (
        .clk(clk), .rst(rst),
        .wr_en(verd_push), .wr_data({c_mal, c_cnt1, c_cnt0, c_tag}),
        .rd_en(verd_pop), .rd_data(verd_q),
        .empty(verd_empty), .full(verd_full), .count()
    );

    always @(posedge clk) begin
        if (rst) begin
            verdict_valid <= 1'b0;
            verdict_mal   <= 1'b0;
            st_mal        <= 32'd0;
            st_last       <= 9'd0;
        end else begin
            verdict_valid <= verd_push;
            verdict_mal   <= verd_push && c_mal;
            if (verd_push) begin
                st_last <= {c_mal, c_cnt1, c_cnt0};
                if (c_mal) st_mal <= st_mal + 1'b1;
            end
        end
    end

    // ============================================================ egress
    reg            e_run, e_fwd;
    reg [LENW-1:0] e_rem;
    reg [8:0]      q;
    reg            q_valid;

    wire consume = q_valid && (e_fwd ? m_axis_tready : 1'b1);
    wire re      = e_run && (e_rem != 0) && (!q_valid || consume);

    assign m_axis_tvalid = q_valid && e_fwd;
    assign m_axis_tdata  = q[7:0];
    assign m_axis_tlast  = q[8];
    assign m_axis_tuser  = 1'b0;

    always @(posedge clk) begin
        if (re)
            q <= buf_mem[rd_ptr[BUF_AW-1:0]];
    end

    always @(*) verd_pop = !e_run && !verd_empty;

    always @(posedge clk) begin
        if (rst) begin
            e_run    <= 1'b0;
            e_fwd    <= 1'b0;
            e_rem    <= 0;
            rd_ptr   <= 0;
            q_valid  <= 1'b0;
            st_pass  <= 32'd0;
            st_block <= 32'd0;
        end else begin
            if (verd_pop) begin
                e_run <= 1'b1;
                e_fwd <= bypass || !drop_en || !verd_q[LENW+8];
                e_rem <= verd_q[LENW-1:0];
                if (bypass || !drop_en || !verd_q[LENW+8]) st_pass  <= st_pass + 1'b1;
                else                                       st_block <= st_block + 1'b1;
            end
            if (re) begin
                rd_ptr <= rd_ptr + 1'b1;
                e_rem  <= e_rem - 1'b1;
            end
            if (re)           q_valid <= 1'b1;
            else if (consume) q_valid <= 1'b0;
            if (e_run && consume && q[8] && e_rem == 0)
                e_run <= 1'b0;
        end
    end

endmodule
