// UART/SLIP-level test of the Tang Nano 9K in-line firewall top (fast UART in sim).
`timescale 1ns/1ps
module tb_tang9k;
    parameter string VEC_DIR = "vectors";
    parameter int CPB = 4;                       // clocks per UART bit (sim speed-up)
    parameter int N_FRAMES = 120;
    parameter int WINDOW = 8;

    logic clk = 0; always #18.5 clk = ~clk;      // 27 MHz
    logic btn_n = 0, rx = 1; wire tx; wire [7:0] leds;

    tang9k_snn_top #(.CLKS_PER_BIT(CPB)) dut (.clk(clk), .rst_n(btn_n), .uart_rx(rx), .uart_tx(tx), .leds_ext(leds));
    // every LED except the slow heartbeat (bit 1) must light at least once during the run
    logic [7:0] led_seen = 0;
    always @(posedge clk) if (btn_n) led_seen <= led_seen | leds;

    typedef byte unsigned frame_t[$];
    frame_t frames[$], got[$];
    int exp_mal[$], verd[$];
    int errors = 0;

    task automatic ubyte(input byte unsigned b);
        rx = 0; repeat (CPB) @(posedge clk);
        for (int i = 0; i < 8; i++) begin rx = b[i]; repeat (CPB) @(posedge clk); end
        rx = 1; repeat (CPB) @(posedge clk);
    endtask
    task automatic slip_send(frame_t m);
        foreach (m[i]) begin
            if (m[i] == 8'hC0) begin ubyte(8'hDB); ubyte(8'hDC); end
            else if (m[i] == 8'hDB) begin ubyte(8'hDB); ubyte(8'hDD); end
            else ubyte(m[i]);
        end
        ubyte(8'hC0);
    endtask

    // ---------------- receiver: UART -> SLIP -> messages
    frame_t msg;
    initial begin
        automatic bit esc = 0;
        forever begin
            byte unsigned b;
            @(negedge tx);
            repeat (CPB + CPB/2) @(posedge clk);
            for (int i = 0; i < 8; i++) begin b[i] = tx; repeat (CPB) @(posedge clk); end
            if (!esc && b == 8'hC0) begin
                if (msg.size() > 0) begin
                    if (msg[0] == "F") begin void'(msg.pop_front()); got.push_back(msg); end
                    else if (msg[0] == "V") verd.push_back(msg[1][7]);
                end
                msg = {};
            end else if (!esc && b == 8'hDB) esc = 1;
            else begin
                msg.push_back(esc ? (b == 8'hDC ? 8'hC0 : 8'hDB) : b);
                esc = 0;
            end
        end
    end

    initial begin
        automatic int fd, len, b, a, d, c0, c1, mal, lab, r; logic [63:0] spk; string kind; frame_t fr;
        fd = $fopen({VEC_DIR, "/frames.txt"}, "r");
        while (frames.size() < N_FRAMES && $fscanf(fd, "%d", len) == 1) begin
            fr = {};
            for (int i = 0; i < len; i++) begin r = $fscanf(fd, "%h", b); fr.push_back(b[7:0]); end
            frames.push_back(fr);
        end
        $fclose(fd);
        fd = $fopen({VEC_DIR, "/expected.txt"}, "r");
        while (exp_mal.size() < N_FRAMES && $fscanf(fd, "%h %d %d %d %d %s", spk, c0, c1, mal, lab, kind) == 6) exp_mal.push_back(mal);
        $fclose(fd);
        repeat (10) @(posedge clk); btn_n = 1; repeat (10) @(posedge clk);
        fd = $fopen({VEC_DIR, "/cfg.txt"}, "r");
        while ($fscanf(fd, "%h %h", a, d) == 2)
            slip_send({"C", a[15:8], a[7:0], d[31:24], d[23:16], d[15:8], d[7:0]});
        $fclose(fd);
        // host flow control: keep at most WINDOW frames in flight
        // (completed = forwarded frames received + malicious verdicts)
        foreach (frames[f]) begin
            automatic int done_n;
            do begin
                done_n = got.size();
                foreach (verd[i]) done_n += verd[i];
                if (f - done_n >= WINDOW) @(posedge clk);
            end while (f - done_n >= WINDOW);
            slip_send({"P", frames[f]});
        end
        repeat (20000 * CPB) @(posedge clk);
        begin
            automatic int k = 0;
            foreach (frames[f]) if (!exp_mal[f]) begin
                if (k >= got.size() || got[k] != frames[f]) begin errors++; if (errors < 5) $display("[ERR] forwarded frame for input %0d wrong/missing", f); end
                k++;
            end
            if (k != got.size()) begin errors++; $display("[ERR] got %0d forwarded, expected %0d", got.size(), k); end
            if (verd.size() != frames.size()) begin errors++; $display("[ERR] %0d verdicts for %0d frames", verd.size(), frames.size()); end
            foreach (verd[i]) if (i < exp_mal.size() && verd[i] != exp_mal[i]) begin errors++; $display("[ERR] verdict %0d", i); end
            if ((led_seen | 8'b0000_0010) != 8'hFF) begin
                errors++; $display("[ERR] LEDs never lit (bit = 0): %08b (heartbeat bit 1 not checked)", led_seen | 8'b0000_0010);
            end
            $display("------------------------------------------------------------");
            $display(" Tang9K LEDs seen lit: %08b (7 attack 6 tx 5 cfg 4 rx 3 blocked 2 fwd 1 heartbeat 0 mal)", led_seen);
            $display(" Tang9K UART: frames=%0d verdicts=%0d forwarded=%0d (expected %0d)", frames.size(), verd.size(), got.size(), k);
            if (errors == 0) $display(" RESULT: PASS (Tang Nano 9K in-line firewall over UART/SLIP)");
            else $display(" RESULT: FAIL (%0d errors)", errors);
            $display("------------------------------------------------------------");
        end
        $finish;
    end
endmodule
