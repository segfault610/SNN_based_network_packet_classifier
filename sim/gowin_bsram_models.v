// Behavioural models of the Gowin GW1N block RAM primitives Yosys emits
// (yosys ships them only as blackboxes). Per Gowin UG285:
//   x9  : address = AD[13:3]          x18 : AD[13:4], byte-enable AD[1:0]
//   x36 : address = AD[13:5], byte-enable AD[3:0] (one bit per 9-bit lane)
//   READ_MODE 0 = bypass (1-cycle registered read), 1 = pipeline (+OCE stage)
//   WRITE_MODE 0 normal (DO holds), 1 write-through, 2 read-before-write
// Only the modes used by this design are modelled (equal widths on both ports).
`timescale 1ns/1ps
module gw_bram_core #(parameter W = 9) ();
endmodule

module SDPX9B (CLKA, CEA, CLKB, CEB, OCE, RESETA, RESETB, ADA, ADB, BLKSELA, BLKSELB, DI, DO);
    parameter READ_MODE = 1'b0;
    parameter BIT_WIDTH_0 = 36;
    parameter BIT_WIDTH_1 = 36;
    parameter BLK_SEL_0 = 3'b000;
    parameter BLK_SEL_1 = 3'b000;
    parameter RESET_MODE = "SYNC";
    input CLKA, CEA, CLKB, CEB, OCE, RESETA, RESETB;
    input [13:0] ADA, ADB;
    input [2:0] BLKSELA, BLKSELB;
    input [35:0] DI;
    output reg [35:0] DO;
    localparam W = BIT_WIDTH_0;
    localparam SH = (W == 36) ? 5 : (W == 18) ? 4 : 3;
    localparam DEPTH = 18432 / W;
    reg [W-1:0] mem [0:DEPTH-1];
    reg [35:0] q;
    integer i;
    initial begin
        if (BIT_WIDTH_0 != BIT_WIDTH_1 || (W != 9 && W != 18 && W != 36)) begin
            $display("SDPX9B model: unsupported widths %0d/%0d", BIT_WIDTH_0, BIT_WIDTH_1); $finish;
        end
        for (i = 0; i < DEPTH; i = i + 1) mem[i] = {W{1'b0}};
        q = 0; DO = 0;
    end
    always @(posedge CLKA)
        if (CEA && BLKSELA == BLK_SEL_0) begin
            if (W == 9) mem[ADA[13:SH]] <= DI[8:0];
            else for (i = 0; i < W / 9; i = i + 1)
                if (ADA[i]) mem[ADA[13:SH]][9*i +: 9] <= DI[9*i +: 9];
        end
    always @(posedge CLKB or posedge RESETB)
        if (RESETB) q <= 0;
        else if (CEB && BLKSELB == BLK_SEL_1) q <= mem[ADB[13:SH]];
    always @(posedge CLKB) if (READ_MODE && OCE) DO <= q;
    always @(*) if (!READ_MODE) DO = q;
endmodule

module DPX9B (CLKA, CEA, OCEA, RESETA, WREA, ADA, DIA, BLKSELA, DOA,
              CLKB, CEB, OCEB, RESETB, WREB, ADB, DIB, BLKSELB, DOB);
    parameter READ_MODE0 = 1'b0;
    parameter READ_MODE1 = 1'b0;
    parameter WRITE_MODE0 = 2'b00;
    parameter WRITE_MODE1 = 2'b00;
    parameter BIT_WIDTH_0 = 18;
    parameter BIT_WIDTH_1 = 18;
    parameter BLK_SEL_0 = 3'b000;
    parameter BLK_SEL_1 = 3'b000;
    parameter RESET_MODE = "SYNC";
    input CLKA, CEA, OCEA, RESETA, WREA, CLKB, CEB, OCEB, RESETB, WREB;
    input [13:0] ADA, ADB;
    input [2:0] BLKSELA, BLKSELB;
    input [17:0] DIA, DIB;
    output [17:0] DOA, DOB;
    localparam W = BIT_WIDTH_0;
    localparam SH = (W == 18) ? 4 : 3;
    localparam DEPTH = 18432 / W;
    reg [W-1:0] mem [0:DEPTH-1];
    reg [17:0] qa, qb;
    integer i;
    initial begin
        if (BIT_WIDTH_0 != BIT_WIDTH_1 || (W != 9 && W != 18) || READ_MODE0 || READ_MODE1) begin
            $display("DPX9B model: unsupported configuration"); $finish;
        end
        for (i = 0; i < DEPTH; i = i + 1) mem[i] = {W{1'b0}};
        qa = 0; qb = 0;
    end
    task automatic port(input we, input [13:0] ad, input [17:0] di, input integer wm, inout [17:0] q);
        begin
            if (we) begin
                if (W == 9) mem[ad[13:SH]] = di[8:0];
                else for (i = 0; i < 2; i = i + 1) if (ad[i]) mem[ad[13:SH]][9*i +: 9] = di[9*i +: 9];
            end
            if (!we || wm == 1) q = mem[ad[13:SH]];          // read / write-through
        end
    endtask
    always @(posedge CLKA or posedge RESETA)
        if (RESETA) qa <= 0;
        else if (CEA && BLKSELA == BLK_SEL_0) begin
            if (WREA && WRITE_MODE0 == 2) qa <= mem[ADA[13:SH]];   // read-before-write
            port(WREA, ADA, DIA, WRITE_MODE0, qa);
        end
    always @(posedge CLKB or posedge RESETB)
        if (RESETB) qb <= 0;
        else if (CEB && BLKSELB == BLK_SEL_1) begin
            if (WREB && WRITE_MODE1 == 2) qb <= mem[ADB[13:SH]];
            port(WREB, ADB, DIB, WRITE_MODE1, qb);
        end
    assign DOA = qa;
    assign DOB = qb;
endmodule
