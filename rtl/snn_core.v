// snn_core
// Event-driven 2-layer LIF spiking neural network (inference).
// Golden model: model/snn_int.py::infer()
//
// Derived from snn_stdp.v (LIF: v <- v - (v >> leak) + I, threshold, reset),
// extended to signed weights, two layers and a weight memory so the
// classifier can be trained offline and loaded at run time.
//
//   Phase ACC : input spikes are static for a packet (direct encoding), so the
//               hidden-layer input current is computed ONCE. Only active inputs
//               are visited (event-driven): one W1 row (N_HID weights) per
//               cycle, all hidden neurons accumulate in parallel.
//   Phase LIF : T_STEPS cycles of hidden LIF dynamics; output layer runs one
//               2 cycles behind (adder tree pipelined) on registered hidden spikes.
//   Decision  : malicious = cnt1 > cnt0 || (cnt1 == cnt0 && v_o1 > v_o0)
//
// Latency ~ (#active inputs) + T_STEPS + 6 cycles per packet.
module snn_core #(
    parameter N_IN   = 64,
    parameter N_HID  = 16,
    parameter V_W    = 20,           // membrane width (two's complement)
    parameter TAG_W  = 16,           // opaque per-packet tag passed through
    parameter W1_INIT = ""           // unused (weights are loaded over the config bus)
)(
    input  wire                 clk,
    input  wire                 rst,

    // runtime parameters
    input  wire [15:0]          th1,          // hidden threshold
    input  wire [15:0]          th2,          // output threshold
    input  wire [3:0]           t_steps,      // timesteps per packet (1..15)
    input  wire [1:0]           leak,         // leak shift
    input  wire [15:0]          b2,           // {b_o1, b_o0} output biases (int8)
    input  wire [N_HID*16-1:0]  w2,           // {.., w[h][o1], w[h][o0]} int8

    // W1 write port: row = input index, lane = group of 4 hidden neurons
    input  wire                 w1_we,
    input  wire [5:0]           w1_row,
    input  wire [1:0]           w1_lane,
    input  wire [31:0]          w1_wdata,     // 4 x int8, neuron 4*lane+k in byte k

    // input spikes
    input  wire                 in_valid,
    output wire                 in_ready,
    input  wire [N_IN-1:0]      in_spikes,
    input  wire [TAG_W-1:0]     in_tag,

    // verdict
    output reg                  out_valid,
    input  wire                 out_ready,
    output reg                  out_mal,
    output reg  [3:0]           out_cnt0,
    output reg  [3:0]           out_cnt1,
    output reg  [TAG_W-1:0]     out_tag
);

    localparam S_IDLE = 2'd0, S_ACC = 2'd1, S_LIF = 2'd2, S_OUT = 2'd3;
    reg [1:0] state;

    // ------------------------------------------------------------ W1 memory
    // N_HID/4 banks of 64 x 32 bit, simple dual port, synchronous read:
    // maps to block RAM on Cyclone V (M10K) / Gowin (BSRAM), SRAM macro in ASIC.
    localparam N_BANK = N_HID / 4;
    wire [N_HID*8-1:0] w1_q;
    reg                rd_en;
    reg [5:0]          rd_row;

    integer k;
    genvar gb;
    generate
        for (gb = 0; gb < N_BANK; gb = gb + 1) begin : g_w1
            reg [31:0] bank [0:N_IN-1];
            reg [31:0] q;
            always @(posedge clk) begin
                if (w1_we && w1_lane == gb)
                    bank[w1_row] <= w1_wdata;
                if (rd_en)
                    q <= bank[rd_row];
            end
            assign w1_q[32*gb +: 32] = q;
        end
    endgenerate

    // ------------------------------------------------------------ event queue
    reg [N_IN-1:0] pend;
    reg [5:0]      pidx;
    reg            pany;
    always @(*) begin            // lowest set bit
        pidx = 6'd0;
        pany = 1'b0;
        for (k = N_IN-1; k >= 0; k = k - 1)
            if (pend[k]) begin
                pidx = k[5:0];
                pany = 1'b1;
            end
    end

    // ------------------------------------------------------------ neuron state
    reg signed [V_W-1:0] acc [0:N_HID-1];   // hidden input current (static)
    reg signed [V_W-1:0] v1  [0:N_HID-1];
    reg [N_HID-1:0]      s1_q;              // hidden spikes of previous step
    reg                  s1_vld;
    reg signed [V_W-1:0] v2  [0:1];
    reg [3:0]            cnt [0:1];
    reg                  rd_vld;            // w1_q holds a row to accumulate
    reg [3:0]            t;
    reg [TAG_W-1:0]      tag;

    wire signed [V_W-1:0] th1_s = {{(V_W-16){1'b0}}, th1};
    wire signed [V_W-1:0] th2_s = {{(V_W-16){1'b0}}, th2};

    // hidden LIF (combinational next state)
    reg signed [V_W-1:0] v1_n [0:N_HID-1];
    reg [N_HID-1:0]      s1_n;
    always @(*) begin
        for (k = 0; k < N_HID; k = k + 1) begin
            v1_n[k] = v1[k] - (v1[k] >>> leak) + acc[k];
            s1_n[k] = (v1_n[k] >= th1_s);
        end
    end

    // output layer: I2 = B2 + sum_h s1[h]*W2[h] as a balanced adder tree,
    // split over two pipeline stages (P1: 16 -> 2 partial sums, registered;
    // P2: 2 partials + bias -> LIF update).  Arithmetic identical to the model.
    localparam N_P = N_HID / 8;                     // N_HID must be a multiple of 8
    // tree nodes sized to their exact range (int8 inputs) for short carry chains
    reg signed [7:0]     m    [0:1][0:N_HID-1];
    reg signed [8:0]     l1   [0:1][0:N_HID/2-1];
    reg signed [9:0]     l2   [0:1][0:N_HID/4-1];
    reg signed [10:0]    l3   [0:1][0:N_P-1];
    reg signed [V_W-1:0] p_q  [0:1][0:N_P-1];      // registered partial sums
    reg                  p_vld;
    reg signed [V_W-1:0] i2   [0:1];
    reg signed [V_W-1:0] v2_n [0:1];
    reg [1:0]            s2_n;
    integer o;
    always @(*) begin
        for (o = 0; o < 2; o = o + 1) begin
            for (k = 0; k < N_HID; k = k + 1)
                m[o][k] = s1_q[k] ? w2[16*k+8*o +: 8] : 8'sd0;
            for (k = 0; k < N_HID/2; k = k + 1)
                l1[o][k] = m[o][2*k] + m[o][2*k+1];
            for (k = 0; k < N_HID/4; k = k + 1)
                l2[o][k] = l1[o][2*k] + l1[o][2*k+1];
            for (k = 0; k < N_P; k = k + 1)
                l3[o][k] = l2[o][2*k] + l2[o][2*k+1];
            i2[o] = {{(V_W-8){b2[8*o+7]}}, b2[8*o +: 8]};
            for (k = 0; k < N_P; k = k + 1)
                i2[o] = i2[o] + p_q[o][k];
            v2_n[o] = v2[o] - (v2[o] >>> leak) + i2[o];
            s2_n[o] = (v2_n[o] >= th2_s);
        end
    end

    assign in_ready = (state == S_IDLE);

    integer ks, os;              // own loop variables: sharing k/o with the always @(*) blocks
                                 // gives yosys a dff + constant driver on them (LibreLane check)
    always @(posedge clk) begin
        if (rst) begin
            state     <= S_IDLE;
            out_valid <= 1'b0;
            out_mal   <= 1'b0;
            out_cnt0  <= 4'd0;
            out_cnt1  <= 4'd0;
            out_tag   <= {TAG_W{1'b0}};
            rd_en     <= 1'b0;
            rd_row    <= 6'd0;
            rd_vld    <= 1'b0;
            pend      <= {N_IN{1'b0}};
            s1_q      <= {N_HID{1'b0}};
            s1_vld    <= 1'b0;
            p_vld     <= 1'b0;
            t         <= 4'd0;
            tag       <= {TAG_W{1'b0}};
            for (ks = 0; ks < N_HID; ks = ks + 1) begin
                acc[ks] <= {V_W{1'b0}};
                v1[ks]  <= {V_W{1'b0}};
            end
            for (os = 0; os < 2; os = os + 1) begin
                v2[os]  <= {V_W{1'b0}};
                cnt[os] <= 4'd0;
            end
        end else begin
            rd_en <= 1'b0;
            case (state)
                // ----------------------------------------------------------
                S_IDLE: begin
                    if (in_valid) begin
                        pend   <= in_spikes;
                        tag    <= in_tag;
                        rd_vld <= 1'b0;
                        for (ks = 0; ks < N_HID; ks = ks + 1) begin
                            acc[ks] <= {V_W{1'b0}};
                            v1[ks]  <= {V_W{1'b0}};
                        end
                        for (os = 0; os < 2; os = os + 1) begin
                            v2[os]  <= {V_W{1'b0}};
                            cnt[os] <= 4'd0;
                        end
                        state <= S_ACC;
                    end
                end
                // ----------------------------------------------------------
                // cycle n  : issue read of row pidx (rd_en registered -> RAM
                //            reads at end of cycle n+1)
                // pipeline : rd_en(n) -> w1_q valid in n+2 -> accumulate
                S_ACC: begin
                    if (pany) begin
                        rd_en  <= 1'b1;
                        rd_row <= pidx;
                        pend   <= pend & (pend - 1'b1);   // clear lowest set bit (= bit pidx)
                    end
                    rd_vld <= rd_en;
                    if (rd_vld)
                        for (ks = 0; ks < N_HID; ks = ks + 1)
                            acc[ks] <= acc[ks] + {{(V_W-8){w1_q[8*ks+7]}}, w1_q[8*ks +: 8]};
                    if (!pany && !rd_en && !rd_vld) begin
                        state  <= S_LIF;
                        t      <= 4'd0;
                        s1_vld <= 1'b0;
                        p_vld  <= 1'b0;
                    end
                end
                // ----------------------------------------------------------
                S_LIF: begin
                    // hidden layer, step t
                    if (t < t_steps) begin
                        for (ks = 0; ks < N_HID; ks = ks + 1)
                            v1[ks] <= s1_n[ks] ? {V_W{1'b0}} : v1_n[ks];
                        s1_q   <= s1_n;
                        s1_vld <= 1'b1;
                        t      <= t + 4'd1;
                    end else begin
                        s1_vld <= 1'b0;
                    end
                    // output layer P1: partial sums of step t-1
                    p_vld <= s1_vld;
                    for (os = 0; os < 2; os = os + 1)
                        for (ks = 0; ks < N_P; ks = ks + 1)
                            p_q[os][ks] <= {{(V_W-11){l3[os][ks][10]}}, l3[os][ks]};
                    // output layer P2: LIF update for step t-2
                    if (p_vld) begin
                        for (os = 0; os < 2; os = os + 1) begin
                            v2[os] <= s2_n[os] ? {V_W{1'b0}} : v2_n[os];
                            if (s2_n[os]) cnt[os] <= cnt[os] + 4'd1;
                        end
                    end
                    if (t >= t_steps && !s1_vld && !p_vld)
                        state <= S_OUT;
                end
                // ----------------------------------------------------------
                S_OUT: begin
                    if (!out_valid) begin
                        out_valid <= 1'b1;
                        out_mal   <= (cnt[1] > cnt[0]) || ((cnt[1] == cnt[0]) && (v2[1] > v2[0]));
                        out_cnt0  <= cnt[0];
                        out_cnt1  <= cnt[1];
                        out_tag   <= tag;
                        state     <= S_IDLE;
                    end
                end
            endcase
            if (out_valid && out_ready)
                out_valid <= 1'b0;
        end
    end

endmodule
