// Avalon-MM wrapper test: emulates the HPS driver (load weights, inject frames
// via TX_WORD/TX_BYTE, drain forwarded frames via RX_POP).
`timescale 1ns/1ps
module tb_snn_fw_avmm;
    parameter string VEC_DIR = "vectors";
    parameter int    N_FRAMES = 150;

    logic clk = 0, reset = 1;
    always #5 clk = ~clk;                       // 100 MHz h2f_user0_clock

    logic [10:0] addr = 0; logic wr = 0, rd = 0; logic [31:0] wdata = 0, rdata; logic wait_req;
    logic [1:0]  leds;

    snn_fw_avmm dut (.clk(clk), .reset(reset), .avs_address(addr), .avs_write(wr), .avs_writedata(wdata),
                     .avs_read(rd), .avs_readdata(rdata), .avs_waitrequest(wait_req), .leds(leds));

    typedef byte unsigned frame_t[$];
    frame_t frames[$], got[$];
    int exp_mal[$];
    int errors = 0;

    task automatic bus_wr(input logic [10:0] a, input logic [31:0] d);
        @(posedge clk); addr <= a; wdata <= d; wr <= 1;
        do @(posedge clk); while (wait_req);
        wr <= 0;
    endtask
    task automatic bus_rd(input logic [10:0] a, output logic [31:0] d);
        @(posedge clk); addr <= a; rd <= 1;
        @(posedge clk); rd <= 0;
        #1 d = rdata;
    endtask

    task automatic load();
        int fd, len, b, c0, c1, mal, lab, r; logic [63:0] spk; string kind; frame_t fr;
        fd = $fopen({VEC_DIR, "/frames.txt"}, "r");
        while (frames.size() < N_FRAMES && $fscanf(fd, "%d", len) == 1) begin
            fr = {};
            for (int i = 0; i < len; i++) begin r = $fscanf(fd, "%h", b); fr.push_back(b[7:0]); end
            frames.push_back(fr);
        end
        $fclose(fd);
        fd = $fopen({VEC_DIR, "/expected.txt"}, "r");
        while (exp_mal.size() < N_FRAMES && $fscanf(fd, "%h %d %d %d %d %s", spk, c0, c1, mal, lab, kind) == 6)
            exp_mal.push_back(mal);
        $fclose(fd);
    endtask

    task automatic drain();
        logic [31:0] d; frame_t cur = {};
        forever begin
            bus_rd(11'h402, d);
            if (!d[9]) break;
            cur.push_back(d[7:0]);
            if (d[8]) begin got.push_back(cur); cur = {}; end
        end
    endtask

    initial begin
        automatic int fd, a, d, k = 0; logic [31:0] id, st[5];
        load();
        repeat (5) @(posedge clk); reset <= 0;
        bus_rd(11'h404, id);
        if (id !== 32'h534E4E31) begin errors++; $display("[ERR] bad ID %h", id); end
        fd = $fopen({VEC_DIR, "/cfg.txt"}, "r");
        while ($fscanf(fd, "%h %h", a, d) == 2) bus_wr(a[10:0], d);
        $fclose(fd);
        foreach (frames[f]) begin
            automatic int n = frames[f].size(), i = 0;
            while (n - i > 4) begin
                bus_wr(11'h401, {frames[f][i+3], frames[f][i+2], frames[f][i+1], frames[f][i]});
                i += 4;
            end
            for (; i < n; i++) bus_wr(11'h400, {23'd0, i == n - 1, frames[f][i]});
            repeat (20) @(posedge clk);
            drain();
        end
        repeat (2000) @(posedge clk);
        drain();
        foreach (frames[f]) if (!exp_mal[f]) begin
            if (k >= got.size() || got[k] != frames[f]) begin errors++; $display("[ERR] frame %0d not forwarded correctly", f); end
            k++;
        end
        if (k != got.size()) begin errors++; $display("[ERR] %0d frames received, %0d expected", got.size(), k); end
        for (int i = 0; i < 5; i++) bus_rd(11'h020 + i, st[i]);
        $display("------------------------------------------------------------");
        $display(" AVMM: injected=%0d forwarded=%0d blocked=%0d (HW counters: in=%0d mal=%0d pass=%0d block=%0d)",
                 frames.size(), got.size(), frames.size() - got.size(), st[0], st[2], st[3], st[4]);
        if (errors == 0) $display(" RESULT: PASS (Avalon-MM / HPS bring-up path)");
        else $display(" RESULT: FAIL (%0d errors)", errors);
        $display("------------------------------------------------------------");
        $finish;
    end
endmodule
