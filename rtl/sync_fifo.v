// sync_fifo: small first-word-fall-through FIFO (register based)
module sync_fifo #(
    parameter W     = 8,
    parameter DEPTH = 4,                 // power of two
    parameter AW    = $clog2(DEPTH)
)(
    input  wire         clk,
    input  wire         rst,
    input  wire         wr_en,
    input  wire [W-1:0] wr_data,
    input  wire         rd_en,
    output wire [W-1:0] rd_data,
    output wire         empty,
    output wire         full,
    output reg  [AW:0]  count
);
    reg [W-1:0] mem [0:DEPTH-1];
    reg [AW-1:0] wp, rp;

    assign empty   = (count == 0);
    assign full    = (count == DEPTH);
    assign rd_data = mem[rp];

    wire do_wr = wr_en && !full;
    wire do_rd = rd_en && !empty;

    always @(posedge clk) begin
        if (rst) begin
            wp <= 0; rp <= 0; count <= 0;
        end else begin
            if (do_wr) begin
                mem[wp] <= wr_data;
                wp <= wp + 1'b1;
            end
            if (do_rd)
                rp <= rp + 1'b1;
            count <= count + do_wr - do_rd;
        end
    end
endmodule
