// Look-aside accelerator test: emulates the Linux kernel hook (sw/cv96/kmod/snn_fw.c):
// poll STATUS.ready -> write <=128 header bytes -> SUBMIT{tag,n,len} -> poll VERDICT.
// Every verdict (mal, spike counts, tag) is checked against the golden model.
`timescale 1ns/1ps
module tb_snn_lookaside;
    parameter string VEC_DIR = "vectors";

    logic clk = 0, reset = 1;
    always #5 clk = ~clk;                       // 100 MHz h2f_user0_clock

    logic [10:0] addr = 0; logic wr = 0, rd = 0; logic [31:0] wdata = 0, rdata;
    logic irq; logic [1:0] leds;

    snn_lookaside_avmm dut (.clk(clk), .reset(reset), .avs_address(addr), .avs_write(wr),
        .avs_writedata(wdata), .avs_read(rd), .avs_readdata(rdata), .irq(irq), .leds(leds));

    typedef byte unsigned frame_t[$];
    frame_t frames[$];
    int exp_c0[$], exp_c1[$], exp_mal[$], exp_lab[$];
    int errors = 0, tp = 0, fp = 0, tn = 0, fn = 0;
    longint t_busy = 0;

    task automatic bus_wr(input logic [10:0] a, input logic [31:0] d);
        @(posedge clk); addr <= a; wdata <= d; wr <= 1;
        @(posedge clk); wr <= 0;
    endtask
    task automatic bus_rd(input logic [10:0] a, output logic [31:0] d);
        @(posedge clk); addr <= a; rd <= 1;
        @(posedge clk); rd <= 0;
        #1 d = rdata;
    endtask

    task automatic load();
        int fd, len, b, c0, c1, mal, lab, r; logic [63:0] spk; string kind; frame_t fr;
        fd = $fopen({VEC_DIR, "/frames.txt"}, "r");
        while ($fscanf(fd, "%d", len) == 1) begin
            fr = {};
            for (int i = 0; i < len; i++) begin r = $fscanf(fd, "%h", b); fr.push_back(b[7:0]); end
            frames.push_back(fr);
        end
        $fclose(fd);
        fd = $fopen({VEC_DIR, "/expected.txt"}, "r");
        while ($fscanf(fd, "%h %d %d %d %d %s", spk, c0, c1, mal, lab, kind) == 6) begin
            exp_c0.push_back(c0); exp_c1.push_back(c1); exp_mal.push_back(mal); exp_lab.push_back(lab);
        end
        $fclose(fd);
    endtask

    initial begin
        automatic int fd, a, d;
        logic [31:0] v, st[4], id;
        load();
        repeat (5) @(posedge clk); reset <= 0;
        bus_rd(11'h423, id);
        if (id !== 32'h534E4E32) begin errors++; $display("[ERR] ID %h", id); end
        fd = $fopen({VEC_DIR, "/cfg.txt"}, "r");
        while ($fscanf(fd, "%h %h", a, d) == 2) bus_wr(a[10:0], d);
        $fclose(fd);
        foreach (frames[f]) begin
            automatic int len = frames[f].size();
            automatic int n = (len > 128) ? 128 : len;
            automatic longint t0 = $time;
            do bus_rd(11'h422, v); while (!v[0]);
            for (int w = 0; w < (n + 3) / 4; w++) begin
                automatic logic [31:0] word = 0;
                for (int k = 0; k < 4; k++) if (4*w + k < n) word[8*k +: 8] = frames[f][4*w + k];
                bus_wr(11'h400 + w, word);
            end
            bus_wr(11'h420, {f[7:0], n[7:0], len[15:0]});
            do bus_rd(11'h421, v); while (!v[31]);
            t_busy += ($time - t0);
            if (v[30] !== exp_mal[f][0] || v[23:20] != exp_c0[f] || v[27:24] != exp_c1[f] || v[7:0] != f[7:0]) begin
                errors++;
                $display("[ERR] frame %0d: hw mal=%0d c0=%0d c1=%0d tag=%0d  exp mal=%0d c0=%0d c1=%0d",
                         f, v[30], v[23:20], v[27:24], v[7:0], exp_mal[f], exp_c0[f], exp_c1[f]);
            end
            if (v[30] && exp_lab[f]) tp++; else if (v[30]) fp++; else if (exp_lab[f]) fn++; else tn++;
        end
        for (int i = 0; i < 4; i++) bus_rd(11'h020 + i, st[i]);
        $display("------------------------------------------------------------");
        $display(" look-aside: frames=%0d submitted=%0d rejected=%0d malicious=%0d", frames.size(), st[0], st[1], st[2]);
        $display(" vs ground truth: TP=%0d FP=%0d TN=%0d FN=%0d", tp, fp, tn, fn);
        $display(" avg bus+classify time per frame (sim bus, 100 MHz): %0d ns", t_busy / frames.size());
        if (errors == 0 && st[0] == frames.size()) $display(" RESULT: PASS (look-aside, bit-exact with golden model)");
        else $display(" RESULT: FAIL (%0d errors)", errors);
        $display("------------------------------------------------------------");
        $finish;
    end
endmodule
