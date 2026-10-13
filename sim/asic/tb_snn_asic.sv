// Functional-verification testbench for the ASIC top, snn_pkt_filter_asic.
//
// Uses ONLY the top-level ports: no hierarchical probes. The same file runs on
//   * the RTL                                   (xrun / vsim)
//   * the Genus tm_netlist_<variant>.v           (zero-delay gate-level)
//   * the Innovus netlist + SDF                  (+define+SDF_FILE=\"...\")
// All TB-driven inputs change on the falling edge, and outputs are sampled on
// the falling edge. Gate-level flops (UDPs) therefore can't race the TB.
//
// Tests (see docs/functional_verification.md for the expected behaviour):
//   T1  reset values           T6  bad-FCS frames (tuser) dropped whole
//   T2  config write/readback  T7  oversized / runt / max-size frames
//   T3  golden bit-exact run   T8  back-to-back line-rate burst
//   T4  monitor mode (CTRL=0)  T9  egress back-pressure + ingress overflow
//   T5  bypass (CTRL=2)        T10 reset in mid-traffic, recovery
`timescale 1ns/1ps
module tb_snn_asic;

    parameter string VEC_DIR_P = "vectors";     // or +VEC_DIR=<path> at run time
    parameter int    SEED      = 1;
    string           VEC_DIR;
    localparam int   BUF_BYTES = 2048;          // snn_pkt_filter_asic: BUF_AW = 11

    // ------------------------------------------------------------ DUT
    logic clk = 0, rst = 1;
    always #4 clk = ~clk;                       // 125 MHz (GMII byte clock)

    logic [7:0]  s_tdata = 0;  logic s_tvalid = 0, s_tlast = 0, s_tuser = 0;
    wire         s_tready;
    wire  [7:0]  m_tdata;      wire m_tvalid, m_tlast, m_tuser;
    logic        m_tready = 0;
    logic        cfg_wr = 0, cfg_rd = 0;
    logic [9:0]  cfg_addr = 0;
    logic [31:0] cfg_wdata = 0;
    wire  [31:0] cfg_rdata;
    wire         verdict_valid, verdict_mal;

    snn_pkt_filter_asic dut (
        .clk(clk), .rst(rst),
        .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
        .s_axis_tlast(s_tlast), .s_axis_tuser(s_tuser),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
        .m_axis_tlast(m_tlast), .m_axis_tuser(m_tuser),
        .cfg_wr(cfg_wr), .cfg_rd(cfg_rd), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .cfg_rdata(cfg_rdata), .verdict_valid(verdict_valid), .verdict_mal(verdict_mal)
    );

`ifdef SDF_FILE
    initial $sdf_annotate(`SDF_FILE, dut, , "sdf.log", "MAXIMUM");
`endif

    // ------------------------------------------------------------ vectors
    typedef byte unsigned frame_t[$];
    frame_t      frames[$];
    int          exp_c0[$], exp_c1[$], exp_mal[$], exp_lab[$];
    int          cfg_a[$], cfg_d[$];

    task automatic load_vectors();
        int fd, len, b, c0, c1, mal, lab, r, a, d;
        logic [63:0] spk;
        string kind;
        frame_t fr;
        fd = $fopen({VEC_DIR, "/frames.txt"}, "r");
        if (fd == 0) $fatal(1, "cannot open %s/frames.txt", VEC_DIR);
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
        fd = $fopen({VEC_DIR, "/cfg.txt"}, "r");
        while ($fscanf(fd, "%h %h", a, d) == 2) begin cfg_a.push_back(a); cfg_d.push_back(d); end
        $fclose(fd);
        if (frames.size() != exp_mal.size() || frames.size() < 250) $fatal(1, "bad vector files");
        $display("[TB] %0d frames, %0d config words", frames.size(), cfg_a.size());
    endtask

    function automatic bit same(frame_t a, frame_t b);
        if (a.size() != b.size()) return 0;
        foreach (a[i]) if (a[i] != b[i]) return 0;
        return 1;
    endfunction

    // ------------------------------------------------------------ bus helpers (falling-edge drive)
    task automatic cfg_write(input logic [9:0] a, input logic [31:0] d);
        @(negedge clk); cfg_wr = 1; cfg_addr = a; cfg_wdata = d;
        @(negedge clk); cfg_wr = 0;
    endtask

    task automatic cfg_read(input logic [9:0] a, output logic [31:0] d);
        @(negedge clk); cfg_rd = 1; cfg_addr = a;
        @(negedge clk); cfg_rd = 0;
        @(negedge clk); d = cfg_rdata;
    endtask

    task automatic load_cfg();
        foreach (cfg_a[i]) cfg_write(cfg_a[i][9:0], cfg_d[i]);
    endtask

    task automatic do_reset();
        @(negedge clk); rst = 1; s_tvalid = 0; s_tlast = 0; s_tuser = 0; cfg_wr = 0; cfg_rd = 0;
        repeat (10) @(negedge clk);
        rst = 0;
        repeat (2) @(negedge clk);
    endtask

    // one frame, MAC-style (no gaps inside the frame; tuser marks bad FCS on the last beat)
    task automatic send(frame_t fr, int ifg, bit bad = 0);
        foreach (fr[i]) begin
            @(negedge clk);
            s_tvalid = 1; s_tdata = fr[i]; s_tlast = (i == fr.size() - 1); s_tuser = bad && s_tlast;
        end
        @(negedge clk); s_tvalid = 0; s_tlast = 0; s_tuser = 0;
        repeat (ifg - 1) @(negedge clk);
    endtask

    // ------------------------------------------------------------ monitors (falling edge)
    int     tready_pct = 100;
    frame_t rx;
    frame_t got[$];          // egress frames
    int     verd[$];         // verdict_mal per verdict_valid pulse
    int     idle = 0, n_tuser = 0;

    always @(negedge clk) begin
        if (rst) begin
            m_tready = 0; rx = {};
        end else begin
            m_tready = ($urandom_range(99, 0) < tready_pct);
            if (m_tvalid && m_tready) begin           // transfer happens at the next rising edge
                rx.push_back(m_tdata);
                if (m_tuser) n_tuser++;
                if (m_tlast) begin got.push_back(rx); rx = {}; end
            end
            if (verdict_valid) verd.push_back(verdict_mal);
        end
        idle = (rst || verdict_valid || m_tvalid || s_tvalid) ? 0 : idle + 1;
    end

    task automatic clear_mon(); got = {}; verd = {}; rx = {}; n_tuser = 0; endtask

    // wait until nothing has moved for 3000 cycles (or give up after `limit` cycles)
    int errors = 0, t_err = 0;
    task automatic wait_idle(int limit = 400000);
        int n = 0;
        while (idle < 3000 && n < limit) begin @(negedge clk); n++; end
        if (n >= limit) begin t_err++; $display("    [ERR] timeout waiting for the DUT to go idle"); end
    endtask

    task automatic chk(bit ok, string msg);
        if (!ok) begin t_err++; $display("    [ERR] %s", msg); end
    endtask

    logic [31:0] st[6];
    task automatic read_stats();
        for (int i = 0; i < 6; i++) cfg_read(10'h020 + i, st[i]);
    endtask

    task automatic begin_test(string name);
        t_err = 0; clear_mon();
        $display("[%s]", name);
    endtask

    task automatic end_test(string name);
        $display("  %-4s %s", t_err ? "FAIL" : "PASS", name);
        errors += t_err;
    endtask

    // run frames[lo..hi] from reset with the trained weights; check verdicts bit-exact
    // and egress = the frames the policy forwards (all of them if forward_all)
    task automatic golden_run(int lo, int hi, int ifg_min, int ifg_max, bit forward_all);
        frame_t exp_out[$];
        int nmal = 0;
        for (int i = lo; i <= hi; i++) begin
            send(frames[i], $urandom_range(ifg_max, ifg_min));
            nmal += exp_mal[i];
            if (forward_all || !exp_mal[i]) exp_out.push_back(frames[i]);
        end
        wait_idle();
        chk(verd.size() == hi - lo + 1, $sformatf("verdicts %0d, expected %0d", verd.size(), hi - lo + 1));
        for (int i = 0; i < verd.size() && i <= hi - lo; i++)
            if (verd[i] != exp_mal[lo + i]) begin
                chk(0, $sformatf("frame %0d verdict mal=%0d, golden %0d", lo + i, verd[i], exp_mal[lo + i])); break;
            end
        chk(got.size() == exp_out.size(), $sformatf("egress %0d frames, expected %0d", got.size(), exp_out.size()));
        for (int i = 0; i < got.size() && i < exp_out.size(); i++)
            if (!same(got[i], exp_out[i])) begin chk(0, $sformatf("egress frame %0d differs", i)); break; end
        chk(n_tuser == 0, "m_axis_tuser asserted");
        read_stats();
        chk(st[0] == hi - lo + 1, $sformatf("committed=%0d", st[0]));
        chk(st[1] == 0,           $sformatf("dropped_ingress=%0d", st[1]));
        chk(st[2] == nmal,        $sformatf("mal counter=%0d, golden %0d", st[2], nmal));
        chk(st[3] == exp_out.size(), $sformatf("forwarded counter=%0d", st[3]));
        chk(st[3] + st[4] == st[0], "forwarded+blocked != committed");
        chk(st[5] == {exp_mal[hi][0], exp_c1[hi][3:0], exp_c0[hi][3:0]},
            $sformatf("last verdict reg %03h, golden %03h", st[5], {exp_mal[hi][0], exp_c1[hi][3:0], exp_c0[hi][3:0]}));
        $display("    frames=%0d mal=%0d forwarded=%0d blocked=%0d", st[0], st[2], st[3], st[4]);
    endtask

    // ------------------------------------------------------------ tests
    initial begin
        logic [31:0] r;
        int tp, fp, tn, fn, nbad;
        frame_t big, runt, maxf;
        void'($urandom(SEED));
        if (!$value$plusargs("VEC_DIR=%s", VEC_DIR)) VEC_DIR = VEC_DIR_P;
        load_vectors();

        // ---------------- T1
        do_reset();
        begin_test("T1 reset values");
        chk(s_tready === 1'b1, "s_axis_tready must be 1 (never back-pressures the MAC)");
        chk(m_tvalid === 1'b0, "m_axis_tvalid must be 0 after reset");
        chk(verdict_valid === 1'b0, "verdict_valid must be 0 after reset");
        cfg_read(10'h000, r); chk(r == 32'h1,  $sformatf("CTRL=%08h, exp 1 (drop_en)", r));
        cfg_read(10'h001, r); chk(r == 32'd256, $sformatf("TH1=%0d, exp 256", r));
        cfg_read(10'h002, r); chk(r == 32'd128, $sformatf("TH2=%0d, exp 128", r));
        cfg_read(10'h003, r); chk(r == 32'h28, $sformatf("TIMING=%08h, exp 28 (leak 2, T 8)", r));
        cfg_read(10'h004, r); chk(r == 32'h0,  $sformatf("B2=%08h, exp 0", r));
        cfg_read(10'h010, r); chk(r == 32'h0,  $sformatf("W2[0]=%08h, exp 0", r));
        read_stats();
        foreach (st[i]) chk(st[i] == 0, $sformatf("stat 0x%03h=%0d, exp 0", 10'h020 + i, st[i]));
        cfg_read(10'h3ff, r); chk(r == 32'h0, "unmapped address must read 0");
        end_test("T1 reset values");

        // ---------------- T2
        begin_test("T2 config write / readback");
        load_cfg();
        foreach (cfg_a[i]) if (cfg_a[i] < 10'h100) begin
            cfg_read(cfg_a[i][9:0], r);
            chk(r == {16'd0, cfg_d[i][15:0]} || (cfg_a[i] == 3 && r == {26'd0, cfg_d[i][5:0]}),
                $sformatf("reg %03h read %08h, wrote %08h", cfg_a[i], r, cfg_d[i]));
        end
        cfg_write(10'h000, 32'h3); cfg_read(10'h000, r); chk(r == 32'h3, "CTRL readback");
        cfg_write(10'h000, 32'h1);
        end_test("T2 config write / readback");

        // ---------------- T3
        begin_test("T3 golden model, bit-exact (drop mode, all vectors)");
        tready_pct = 90;
        golden_run(0, frames.size() - 1, 12, 40, 0);
        tp = 0; fp = 0; tn = 0; fn = 0;
        foreach (verd[i]) if (verd[i] && exp_lab[i]) tp++; else if (verd[i]) fp++; else if (exp_lab[i]) fn++; else tn++;
        $display("    vs ground truth: TP=%0d FP=%0d TN=%0d FN=%0d", tp, fp, tn, fn);
        end_test("T3 golden model, bit-exact (drop mode, all vectors)");

        // ---------------- T4
        do_reset(); load_cfg(); cfg_write(10'h000, 32'h0);
        begin_test("T4 monitor mode CTRL.drop_en=0 (classify, forward all)");
        golden_run(0, 149, 12, 40, 1);
        chk(st[4] == 0, "blocked must be 0 in monitor mode");
        end_test("T4 monitor mode CTRL.drop_en=0 (classify, forward all)");

        // ---------------- T5
        do_reset(); load_cfg(); cfg_write(10'h000, 32'h3);
        begin_test("T5 bypass CTRL.bypass=1 (forward all)");
        golden_run(0, 149, 12, 40, 1);
        chk(st[4] == 0, "blocked must be 0 in bypass");
        end_test("T5 bypass CTRL.bypass=1 (forward all)");

        // ---------------- T6
        do_reset(); load_cfg();
        begin_test("T6 bad-FCS frames (tuser on last beat) dropped whole");
        tready_pct = 100; nbad = 0;
        for (int i = 0; i < 100; i++) begin
            send(frames[i], 16, (i % 5) == 4);
            nbad += ((i % 5) == 4);
        end
        wait_idle();
        read_stats();
        chk(st[1] == nbad, $sformatf("dropped_ingress=%0d, exp %0d", st[1], nbad));
        chk(st[0] == 100 - nbad, $sformatf("committed=%0d, exp %0d", st[0], 100 - nbad));
        chk(verd.size() == 100 - nbad, $sformatf("verdicts=%0d, exp %0d (one per committed frame)", verd.size(), 100 - nbad));
        chk(st[3] + st[4] == st[0], "forwarded+blocked != committed");
        chk(got.size() == st[3], "egress count != forwarded counter");
        begin   // egress = in-order subsequence of the good frames only
            automatic int p = 0;
            foreach (got[k]) begin
                while (p < 100 && !((p % 5) != 4 && same(got[k], frames[p]))) p++;
                chk(p < 100, $sformatf("egress frame %0d is not an in-order good frame", k));
                p++;
            end
        end
        $display("    sent=100 bad=%0d committed=%0d forwarded=%0d blocked=%0d", nbad, st[0], st[3], st[4]);
        end_test("T6 bad-FCS frames (tuser on last beat) dropped whole");

        // ---------------- T7
        do_reset(); load_cfg(); cfg_write(10'h000, 32'h0);   // monitor mode: every committed frame must come out intact
        begin_test("T7 oversized (> buffer), runt and 1518-byte frames");
        big = frames[0];  while (big.size() < BUF_BYTES + 100) big.push_back(8'hA5);
        maxf = frames[0]; while (maxf.size() < 1518) maxf.push_back(8'h5A);
        runt = {};        for (int i = 0; i < 8; i++) runt.push_back(frames[0][i]);
        send(big, 16);  send(runt, 16);  send(maxf, 16);
        for (int i = 0; i < 10; i++) send(frames[i], 16);
        wait_idle();
        read_stats();
        chk(st[1] == 1,  $sformatf("dropped_ingress=%0d, exp 1 (the oversized frame)", st[1]));
        chk(st[0] == 12, $sformatf("committed=%0d, exp 12", st[0]));
        chk(verd.size() == 12, $sformatf("verdicts=%0d, exp 12", verd.size()));
        chk(got.size() == 12, $sformatf("egress=%0d, exp 12", got.size()));
        if (got.size() == 12) begin
            chk(same(got[0], runt), "runt frame corrupted");
            chk(same(got[1], maxf), "1518-byte frame corrupted");
            for (int i = 0; i < 10; i++) chk(same(got[2 + i], frames[i]), $sformatf("frame %0d after the drop corrupted", i));
        end
        end_test("T7 oversized (> buffer), runt and 1518-byte frames");

        // ---------------- T8
        do_reset(); load_cfg();
        begin_test("T8 back-to-back burst, minimum IFG, 250 frames");
        tready_pct = 100;
        golden_run(0, 249, 20, 20, 0);   // 20 idle cycles = 12 B IFG + 8 B preamble
        end_test("T8 back-to-back burst, minimum IFG, 250 frames");

        // ---------------- T9
        do_reset(); load_cfg();
        begin_test("T9 egress back-pressure 35% + IFG 1..3 (forces ingress drops)");
        tready_pct = 35;
        foreach (frames[i]) send(frames[i], $urandom_range(3, 1));
        wait_idle();
        read_stats();
        chk(st[0] + st[1] == frames.size(), "committed + dropped != frames sent");
        chk(st[3] + st[4] == st[0],         "forwarded + blocked != committed");
        chk(verd.size() == st[0],           "verdict pulses != committed");
        chk(got.size() == st[3],            "egress frames != forwarded counter");
        chk(st[1] > 0,                      "expected some ingress drops under overload");
        begin
            automatic int p = 0;
            foreach (got[k]) begin
                while (p < frames.size() && !same(got[k], frames[p])) p++;
                chk(p < frames.size(), $sformatf("egress frame %0d is not an in-order input frame", k));
                p++;
            end
        end
        $display("    sent=%0d committed=%0d dropped=%0d forwarded=%0d blocked=%0d", frames.size(), st[0], st[1], st[3], st[4]);
        end_test("T9 egress back-pressure 35% + IFG 1..3 (forces ingress drops)");

        // ---------------- T10
        do_reset(); load_cfg();
        begin_test("T10 reset in mid-frame / mid-egress, then recovery");
        tready_pct = 20;
        for (int i = 0; i < 6; i++) send(frames[i], 2);
        for (int i = 0; i < frames[6].size() / 2; i++) begin     // half a frame, then reset
            @(negedge clk); s_tvalid = 1; s_tdata = frames[6][i]; s_tlast = 0;
        end
        @(negedge clk); rst = 1; s_tvalid = 0;
        repeat (3) @(negedge clk);
        chk(m_tvalid === 1'b0, "m_axis_tvalid must drop during reset");
        repeat (7) @(negedge clk); rst = 0; repeat (2) @(negedge clk);
        clear_mon();
        read_stats();
        foreach (st[i]) chk(st[i] == 0, $sformatf("stat 0x%03h=%0d after reset", 10'h020 + i, st[i]));
        load_cfg();
        tready_pct = 90;
        golden_run(0, 59, 12, 40, 0);
        end_test("T10 reset in mid-frame / mid-egress, then recovery");

        $display("============================================================");
        if (errors == 0) $display(" RESULT: PASS (10 tests)");
        else             $display(" RESULT: FAIL (%0d errors)", errors);
        $display("============================================================");
        $finish;
    end

endmodule
