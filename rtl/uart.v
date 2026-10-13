// Minimal 8N1 UART receiver / transmitter (CLKS_PER_BIT = f_clk / baud)
module uart_rx #(parameter CLKS_PER_BIT = 27) (
    input  wire       clk,
    input  wire       rst,
    input  wire       rx,
    output reg  [7:0] data,
    output reg        valid
);
    localparam CW = $clog2(CLKS_PER_BIT * 3 / 2 + 1);
    reg [1:0]    sync;
    reg [CW-1:0] cnt;
    reg [3:0]    bitn;
    reg          busy;
    always @(posedge clk) begin
        if (rst) begin
            sync <= 2'b11; cnt <= 0; bitn <= 0; busy <= 1'b0; valid <= 1'b0; data <= 8'd0;
        end else begin
            sync  <= {sync[0], rx};
            valid <= 1'b0;
            if (!busy) begin
                if (!sync[1]) begin                       // start bit edge
                    busy <= 1'b1;
                    cnt  <= CLKS_PER_BIT + CLKS_PER_BIT / 2 - 1;   // sample middle of bit 0
                    bitn <= 4'd0;
                end
            end else if (cnt != 0) begin
                cnt <= cnt - 1'b1;
            end else if (bitn < 4'd8) begin
                data <= {sync[1], data[7:1]};
                bitn <= bitn + 1'b1;
                cnt  <= CLKS_PER_BIT - 1;
            end else begin                                // stop bit
                busy  <= 1'b0;
                valid <= sync[1];
            end
        end
    end
endmodule

module uart_tx #(parameter CLKS_PER_BIT = 27) (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] data,
    input  wire       valid,
    output wire       ready,
    output reg        tx
);
    localparam CW = $clog2(CLKS_PER_BIT + 1);
    reg [CW-1:0] cnt;
    reg [3:0]    bitn;
    reg [9:0]    sh;
    reg          busy;
    assign ready = !busy;
    always @(posedge clk) begin
        if (rst) begin
            tx <= 1'b1; busy <= 1'b0; cnt <= 0; bitn <= 0; sh <= 10'h3FF;
        end else if (!busy) begin
            if (valid) begin
                sh <= {1'b1, data, 1'b0}; busy <= 1'b1; bitn <= 0; cnt <= 0;
            end
        end else if (cnt != 0) begin
            cnt <= cnt - 1'b1;
        end else if (bitn == 4'd10) begin
            busy <= 1'b0;
        end else begin
            tx   <= sh[0];
            sh   <= {1'b1, sh[9:1]};
            bitn <= bitn + 1'b1;
            cnt  <= CLKS_PER_BIT - 1;
        end
    end
endmodule
