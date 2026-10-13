// spike_encoder
// Header fields -> 64 binary input spikes (direct/population coding) plus a
// sliding-window rate monitor (pure-SYN and ICMP echo-request frames).
// Golden model: model/pktfeat.py::encode()/RateMonitor
//
// The vector is registered: spk_valid pulses one cycle after `done & commit`.
module spike_encoder #(
    parameter RATE_WIN = 32,
    parameter RATE_T1  = 8,
    parameter RATE_T2  = 16
)(
    input  wire        clk,
    input  wire        rst,

    input  wire        done,       // parser done (fields valid this cycle)
    input  wire        commit,     // frame accepted into the buffer
    input  wire [15:0] flen,
    input  wire [15:0] ethertype,
    input  wire        vlan,
    input  wire [3:0]  ihl,
    input  wire [15:0] tot_len,
    input  wire        df,
    input  wire        mf,
    input  wire [12:0] foff,
    input  wire [7:0]  ttl,
    input  wire [7:0]  proto,
    input  wire [31:0] src_ip,
    input  wire [31:0] dst_ip,
    input  wire        has_l4,
    input  wire [15:0] sport,
    input  wire [15:0] dport,
    input  wire [3:0]  doff,
    input  wire [7:0]  tflags,
    input  wire [15:0] win,

    output reg         spk_valid,
    output reg  [63:0] spikes
);

    localparam CW = $clog2(RATE_WIN + 1);

    // ------------------------------------------------------------ decode
    wire ipv4 = (ethertype == 16'h0800);
    wire arp  = (ethertype == 16'h0806);
    wire ipv6 = (ethertype == 16'h86DD);
    wire tcp  = ipv4 && (proto == 8'd6);
    wire udp  = ipv4 && (proto == 8'd17);
    wire icmp = ipv4 && (proto == 8'd1);
    wire l4ok = ipv4 && has_l4;
    wire [7:0] icmp_type = sport[15:8];

    // signed 18-bit length arithmetic
    wire signed [17:0] s_flen = {2'b00, flen};
    wire signed [17:0] s_l3   = vlan ? 18'sd18 : 18'sd14;
    wire signed [17:0] s_tot  = {2'b00, tot_len};
    wire signed [17:0] s_ihl4 = {12'd0, ihl, 2'b00};
    wire signed [17:0] s_pl   = s_tot - s_ihl4;            // IP payload length
    wire signed [17:0] s_l4   = s_l3 + s_ihl4;
    wire signed [17:0] s_need = tcp ? 18'sd20 : udp ? 18'sd8 : icmp ? 18'sd4 : 18'sd0;

    wire trunc = ipv4 ? ((s_flen < s_l3 + 18'sd20) || (has_l4 && (s_flen < s_l4 + s_need)))
                      : (s_flen < s_l3);

    // ------------------------------------------------------------ rate monitor
    wire ev_syn  = l4ok && tcp  && ((tflags & 8'h12) == 8'h02);
    wire ev_echo = l4ok && icmp && (icmp_type == 8'd8);

    reg  [RATE_WIN-1:0] syn_win, echo_win;
    reg  [CW-1:0]       syn_cnt, echo_cnt;
    wire [CW-1:0] syn_cnt_n  = syn_cnt  + ev_syn  - syn_win[RATE_WIN-1];
    wire [CW-1:0] echo_cnt_n = echo_cnt + ev_echo - echo_win[RATE_WIN-1];

    // ------------------------------------------------------------ spike vector
    reg [63:0] s;
    always @(*) begin
        s = 64'd0;
        s[0] = 1'b1;
        s[1] = ipv4;
        s[2] = arp;
        s[3] = ipv6;
        s[4] = !(ipv4 || arp || ipv6);
        if (ipv4) begin
            s[5] = tcp; s[6] = udp; s[7] = icmp; s[8] = !(tcp || udp || icmp);
            s[9]  = (ihl == 4'd5); s[10] = (ihl > 4'd5); s[11] = (ihl < 4'd5);
            s[12] = df; s[13] = mf; s[14] = (foff != 13'd0);
            s[15] = (ttl <= 8'd8);
            s[16] = (ttl >= 8'd9)  && (ttl <= 8'd64);
            s[17] = (ttl >= 8'd65) && (ttl <= 8'd128);
            s[18] = (ttl > 8'd128);
            s[19] = (tot_len <= 16'd40);
            s[20] = (tot_len >= 16'd41)  && (tot_len <= 16'd100);
            s[21] = (tot_len >= 16'd101) && (tot_len <= 16'd576);
            s[22] = (tot_len >= 16'd577) && (tot_len <= 16'd1500);
            s[23] = (tot_len > 16'd1500);
            s[24] = (src_ip == dst_ip);
            s[25] = (src_ip[31:24] == 8'd0) || (src_ip[31:24] == 8'd127) || (src_ip[31:24] >= 8'd224);
            s[26] = (dst_ip[7:0] == 8'd255);
            if (tcp && has_l4) begin
                s[32:27] = tflags[5:0];               // FIN SYN RST PSH ACK URG
                s[33] = (tflags[5:0] == 6'd0);
                s[42] = (doff == 4'd5); s[43] = (doff > 4'd5); s[44] = (doff < 4'd5);
                s[45] = (win == 16'd0);
                s[46] = (win >= 16'd1) && (win <= 16'd1023);
                s[47] = (win >= 16'd1024);
            end
            if ((tcp || udp) && has_l4) begin
                s[34] = (dport == 16'd0);
                s[35] = (dport >= 16'd1)    && (dport <= 16'd1023);
                s[36] = (dport >= 16'd1024) && (dport <= 16'd49151);
                s[37] = (dport >= 16'd49152);
                s[38] = (sport == 16'd0);
                s[39] = (sport >= 16'd1)    && (sport <= 16'd1023);
                s[40] = (sport >= 16'd1024) && (sport <= 16'd49151);
                s[41] = (sport >= 16'd49152);
                s[62] = (dport == 16'd22) || (dport == 16'd23) || (dport == 16'd445) || (dport == 16'd3389);
                s[63] = (dport == 16'd53) || (sport == 16'd53);
            end
            if (icmp && has_l4) begin
                s[48] = (icmp_type == 8'd0);
                s[49] = (icmp_type == 8'd8);
                s[50] = (icmp_type == 8'd3);
                s[51] = !((icmp_type == 8'd0) || (icmp_type == 8'd3) || (icmp_type == 8'd8));
            end
            s[52] = (s_pl <= 18'sd8);
            s[53] = (s_pl >= 18'sd9)  && (s_pl <= 18'sd64);
            s[54] = (s_pl >= 18'sd65) && (s_pl <= 18'sd512);
            s[55] = (s_pl > 18'sd512);
            s[56] = (s_tot > s_flen - s_l3) || (s_tot < s_ihl4);
        end
        s[57] = (syn_cnt_n  >= RATE_T1);
        s[58] = (syn_cnt_n  >= RATE_T2);
        s[59] = (echo_cnt_n >= RATE_T1);
        s[60] = (echo_cnt_n >= RATE_T2);
        s[61] = trunc;
    end

    always @(posedge clk) begin
        if (rst) begin
            spk_valid <= 1'b0;
            spikes    <= 64'd0;
            syn_win   <= {RATE_WIN{1'b0}};
            echo_win  <= {RATE_WIN{1'b0}};
            syn_cnt   <= {CW{1'b0}};
            echo_cnt  <= {CW{1'b0}};
        end else begin
            spk_valid <= 1'b0;
            if (done && commit) begin
                spk_valid <= 1'b1;
                spikes    <= s;
                syn_win   <= {syn_win[RATE_WIN-2:0],  ev_syn};
                echo_win  <= {echo_win[RATE_WIN-2:0], ev_echo};
                syn_cnt   <= syn_cnt_n;
                echo_cnt  <= echo_cnt_n;
            end
        end
    end

endmodule
