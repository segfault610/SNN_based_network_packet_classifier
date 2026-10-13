// pkt_parser
// Streaming Ethernet/IPv4/L4 header field extractor (8-bit AXI-Stream beat).
// Golden model: model/pktfeat.py::parse()
//
// * Observes beats (beat = valid & ready of the surrounding datapath).
// * Supports one 802.1Q VLAN tag, IPv4 options (IHL), TCP/UDP/ICMP.
// * All field registers are cleared on the first beat of every frame, so
//   fields of truncated frames read as zero (same as the model).
// * done pulses for one cycle after the tlast beat; fields stay stable until
//   the first beat of the next frame.
module pkt_parser (
    input  wire        clk,
    input  wire        rst,

    input  wire [7:0]  beat_data,
    input  wire        beat_valid,
    input  wire        beat_last,

    output reg         done,
    output reg  [15:0] flen,       // frame length in bytes (saturating)
    output wire [15:0] ethertype,  // inner ethertype (after VLAN tag)
    output wire        vlan,
    output reg  [3:0]  ihl,
    output reg  [15:0] tot_len,
    output reg         df,
    output reg         mf,
    output reg  [12:0] foff,
    output reg  [7:0]  ttl,
    output reg  [7:0]  proto,
    output reg  [31:0] src_ip,
    output reg  [31:0] dst_ip,
    output wire        has_l4,
    output reg  [15:0] sport,      // sport[15:8] doubles as ICMP type
    output reg  [15:0] dport,
    output reg  [3:0]  doff,
    output reg  [7:0]  tflags,
    output reg  [15:0] win
);

    reg  [15:0] cnt;       // index of the current byte within the frame
    reg  [15:0] et0, et1;

    assign vlan      = (et0 == 16'h8100);
    assign ethertype = vlan ? et1 : et0;
    assign has_l4    = (ihl >= 4'd5) && (foff == 13'd0);

    wire [15:0] l3     = vlan ? 16'd18 : 16'd14;
    wire [15:0] rel    = cnt - l3;                    // offset into IPv4 header
    wire [15:0] l4     = l3 + {10'd0, ihl, 2'b00};
    wire [15:0] l4rel  = cnt - l4;                    // offset into L4 header
    wire        in_ip  = (cnt >= l3);
    wire        in_l4  = has_l4 && (cnt >= l4);

    always @(posedge clk) begin
        if (rst) begin
            cnt  <= 16'd0;
            done <= 1'b0;
            flen <= 16'd0;
            et0 <= 16'd0; et1 <= 16'd0;
            ihl <= 4'd0; tot_len <= 16'd0; df <= 1'b0; mf <= 1'b0; foff <= 13'd0;
            ttl <= 8'd0; proto <= 8'd0; src_ip <= 32'd0; dst_ip <= 32'd0;
            sport <= 16'd0; dport <= 16'd0; doff <= 4'd0; tflags <= 8'd0; win <= 16'd0;
        end else begin
            done <= 1'b0;
            if (beat_valid) begin
                if (cnt == 16'd0) begin
                    // new frame: clear all captured fields (byte 0 captures nothing)
                    et0 <= 16'd0; et1 <= 16'd0;
                    ihl <= 4'd0; tot_len <= 16'd0; df <= 1'b0; mf <= 1'b0; foff <= 13'd0;
                    ttl <= 8'd0; proto <= 8'd0; src_ip <= 32'd0; dst_ip <= 32'd0;
                    sport <= 16'd0; dport <= 16'd0; doff <= 4'd0; tflags <= 8'd0; win <= 16'd0;
                end

                // ---------------- Ethernet / VLAN
                if (cnt == 16'd12) et0[15:8] <= beat_data;
                if (cnt == 16'd13) et0[7:0]  <= beat_data;
                if (cnt == 16'd16) et1[15:8] <= beat_data;
                if (cnt == 16'd17) et1[7:0]  <= beat_data;

                // ---------------- IPv4 header (captured unconditionally,
                // qualified by ethertype in the encoder)
                if (in_ip) begin
                    case (rel)
                        16'd0:  ihl          <= beat_data[3:0];
                        16'd2:  tot_len[15:8] <= beat_data;
                        16'd3:  tot_len[7:0]  <= beat_data;
                        16'd6:  begin df <= beat_data[6]; mf <= beat_data[5]; foff[12:8] <= beat_data[4:0]; end
                        16'd7:  foff[7:0]    <= beat_data;
                        16'd8:  ttl          <= beat_data;
                        16'd9:  proto        <= beat_data;
                        16'd12: src_ip[31:24] <= beat_data;
                        16'd13: src_ip[23:16] <= beat_data;
                        16'd14: src_ip[15:8]  <= beat_data;
                        16'd15: src_ip[7:0]   <= beat_data;
                        16'd16: dst_ip[31:24] <= beat_data;
                        16'd17: dst_ip[23:16] <= beat_data;
                        16'd18: dst_ip[15:8]  <= beat_data;
                        16'd19: dst_ip[7:0]   <= beat_data;
                        default: ;
                    endcase
                end

                // ---------------- L4 header (first fragment, IHL >= 5 only)
                if (in_l4) begin
                    case (l4rel)
                        16'd0:  sport[15:8] <= beat_data;
                        16'd1:  sport[7:0]  <= beat_data;
                        16'd2:  dport[15:8] <= beat_data;
                        16'd3:  dport[7:0]  <= beat_data;
                        16'd12: doff        <= beat_data[7:4];
                        16'd13: tflags      <= beat_data;
                        16'd14: win[15:8]   <= beat_data;
                        16'd15: win[7:0]    <= beat_data;
                        default: ;
                    endcase
                end

                if (beat_last) begin
                    flen <= (cnt == 16'hFFFF) ? 16'hFFFF : cnt + 16'd1;
                    cnt  <= 16'd0;
                    done <= 1'b1;
                end else if (cnt != 16'hFFFF) begin
                    cnt <= cnt + 16'd1;
                end
            end
        end
    end

endmodule
