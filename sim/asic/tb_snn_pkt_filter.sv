// Self-checking testbench for snn_pkt_filter.
//  * loads trained weights through the config bus (cfg.txt)
//  * streams frames (frames.txt) MAC-style: no backpressure, random IFG
//  * checks every spike vector and every SNN verdict bit-exactly against the
//    Python golden model (expected.txt)
//  * checks the egress stream: exactly the frames with verdict benign, in
//    order, byte-identical; random m_axis_tready backpressure
`timescale 1ns/1ps
module tb_snn_pkt_filter;

    parameter string VEC_DIR = "vectors";
    parameter int    TREADY_PCT = 90;
    parameter int    IFG_MIN = 12, IFG_MAX = 40;
    // STRESS=1: heavy egress backpressure + tiny IFG -> forces ingress drops.
    // Golden-model checks are replaced by integrity checks (egress frames must
    // be an in-order subsequence of the input, counters must balance).
    parameter bit    STRESS = 0;

    logic clk = 0, rst = 1;
    always #4 clk = ~clk;                 // 125 MHz (1 GbE GMII byte clock)

    logic [7:0]  s_tdata;  logic s_tvalid, s_tlast, s_tuser, s_tready;
    logic [7:0]  m_tdata;  logic m_tvalid, m_tlast, m_tuser, m_tready;
    logic        cfg_wr = 0, cfg_rd = 0;
    logic [9:0]  cfg_addr = 0;
    logic [31:0] cfg_wdata = 0, cfg_rdata;
    logic        verdict_valid, verdict_mal;

    snn_pkt_filter dut (
        .clk(clk), .rst(rst),
        .s_axis_tdata(s_tdata), .s_axis_tvalid(s_tvalid), .s_axis_tready(s_tready),
        .s_axis_tlast(s_tlast), .s_axis_tuser(s_tuser),
        .m_axis_tdata(m_tdata), .m_axis_tvalid(m_tvalid), .m_axis_tready(m_tready),
        .m_axis_tlast(m_tlast), .m_axis_tuser(m_tuser),
        .cfg_wr(cfg_wr), .cfg_rd(cfg_rd), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .cfg_rdata(cfg_rdata), .verdict_valid(verdict_valid), .verdict_mal(verdict_mal)
    );

    // ------------------------------------------------------------ vectors
    typedef byte unsigned frame_t[$];
    frame_t      frames[$];
    logic [63:0] exp_spk[$];
    int          exp_c0[$], exp_c1[$], exp_mal[$], exp_lab[$];
    string       exp_kind[$];
    int          fwd_idx[$];              // indices of frames expected at egress

    int errors = 0;

    task automatic load_vectors();
        int fd, n, len, b, c0, c1, mal, lab, r;
        logic [63:0] spk;
        string kind;
        frame_t fr;
        fd = $fopen({VEC_DIR, "/frames.txt"}, "r");
        if (fd == 0) $fatal(1, "cannot open frames.txt");
        while ($fscanf(fd, "%d", len) == 1) begin
            fr = {};
            for (int i = 0; i < len; i++) begin
                r = $fscanf(fd, "%h", b);
                fr.push_back(b[7:0]);
            end
            frames.push_back(fr);
        end
        $fclose(fd);
        fd = $fopen({VEC_DIR, "/expected.txt"}, "r");
        while ($fscanf(fd, "%h %d %d %d %d %s", spk, c0, c1, mal, lab, kind) == 6) begin
            exp_spk.push_back(spk); exp_c0.push_back(c0); exp_c1.push_back(c1);
            exp_mal.push_back(mal); exp_lab.push_back(lab); exp_kind.push_back(kind);
        end
        $fclose(fd);
        if (frames.size() != exp_spk.size()) $fatal(1, "vector count mismatch");
        foreach (exp_mal[i]) if (!exp_mal[i]) fwd_idx.push_back(i);
        $display("[TB] loaded %0d frames, %0d expected to be forwarded", frames.size(), fwd_idx.size());
    endtask

    task automatic cfg_write(input logic [9:0] a, input logic [31:0] d);
        @(posedge clk); cfg_wr <= 1; cfg_addr <= a; cfg_wdata <= d;
        @(posedge clk); cfg_wr <= 0;
    endtask

    task automatic cfg_read(input logic [9:0] a, output logic [31:0] d);
        @(posedge clk); cfg_rd <= 1; cfg_addr <= a;
        @(posedge clk); cfg_rd <= 0;
        @(negedge clk); d = cfg_rdata;
    endtask

    task automatic load_cfg();
        int fd, a, d, n = 0;
        fd = $fopen({VEC_DIR, "/cfg.txt"}, "r");
        if (fd == 0) $fatal(1, "cannot open cfg.txt");
        while ($fscanf(fd, "%h %h", a, d) == 2) begin
            cfg_write(a[9:0], d);
            n++;
        end
        $fclose(fd);
        $display("[TB] %0d config writes done", n);
    endtask

    // ------------------------------------------------------------ driver
    task automatic drive();
        foreach (frames[f]) begin
            for (int i = 0; i < frames[f].size(); i++) begin
                @(posedge clk);
                s_tvalid <= 1; s_tdata <= frames[f][i];
                s_tlast  <= (i == frames[f].size() - 1); s_tuser <= 0;
            end
            @(posedge clk);
            s_tvalid <= 0; s_tlast <= 0;
            repeat ($urandom_range(IFG_MAX, IFG_MIN) - 1) @(posedge clk);
        end
    endtask

    // ------------------------------------------------------------ monitors
    int n_spk = 0, n_verd = 0, n_out = 0;
    int tp = 0, fp = 0, tn = 0, fn = 0;

    always @(posedge clk) if (!rst && !STRESS && dut.u_cls.spk_valid) begin
        if (dut.u_cls.spikes !== exp_spk[n_spk]) begin
            errors++;
            $display("[ERR] frame %0d (%s) spikes: rtl %016h exp %016h diff %016h", n_spk,
                     exp_kind[n_spk], dut.u_cls.spikes, exp_spk[n_spk], dut.u_cls.spikes ^ exp_spk[n_spk]);
        end
        n_spk++;
    end

    always @(posedge clk) if (!rst && STRESS && dut.verd_push) n_verd++;
    always @(posedge clk) if (!rst && !STRESS && dut.verd_push) begin
        automatic int i = n_verd;
        if (dut.c_mal !== exp_mal[i][0] || dut.c_cnt0 != exp_c0[i] || dut.c_cnt1 != exp_c1[i] ||
            dut.c_tag != frames[i].size()) begin
            errors++;
            $display("[ERR] frame %0d verdict: rtl mal=%0d c0=%0d c1=%0d len=%0d  exp mal=%0d c0=%0d c1=%0d len=%0d",
                     i, dut.c_mal, dut.c_cnt0, dut.c_cnt1, dut.c_tag, exp_mal[i], exp_c0[i], exp_c1[i], frames[i].size());
        end
        if (dut.c_mal && exp_lab[i]) tp++; else if (dut.c_mal) fp++;
        else if (exp_lab[i]) fn++; else tn++;
        n_verd++;
    end

    frame_t rx;
    int     stress_pos = 0;
    always @(posedge clk) begin
        if (rst) m_tready <= 0;
        else     m_tready <= ($urandom_range(99, 0) < TREADY_PCT);
    end
    always @(posedge clk) if (!rst && m_tvalid && m_tready) begin
        rx.push_back(m_tdata);
        if (m_tlast && STRESS) begin
            while (stress_pos < frames.size() && rx != frames[stress_pos]) stress_pos++;
            if (stress_pos == frames.size()) begin
                errors++; $display("[ERR] egress frame %0d is not an in-order input frame", n_out);
            end
            stress_pos++;
            n_out++;
            rx = {};
        end else if (m_tlast) begin
            if (n_out >= fwd_idx.size()) begin
                errors++; $display("[ERR] unexpected extra egress frame");
            end else if (rx != frames[fwd_idx[n_out]]) begin
                errors++;
                $display("[ERR] egress frame %0d (input #%0d) mismatch: got %0d bytes exp %0d",
                         n_out, fwd_idx[n_out], rx.size(), frames[fwd_idx[n_out]].size());
            end
            n_out++;
            rx = {};
        end
    end

    // ------------------------------------------------------------ main
    initial begin
        logic [31:0] st[6];
        s_tvalid = 0; s_tlast = 0; s_tuser = 0; s_tdata = 0;
        load_vectors();
        repeat (5) @(posedge clk);
        rst <= 0;
        load_cfg();
        drive();
        fork
            if (STRESS) wait (n_verd == dut.st_in && dut.e_run == 0 && dut.verd_empty && !m_tvalid &&
                              n_out == dut.st_pass);
            else wait (n_out == fwd_idx.size() && n_verd == frames.size());
            begin repeat (200000) @(posedge clk); $display("[ERR] timeout"); errors++; end
        join_any
        disable fork;
        repeat (20) @(posedge clk);
        for (int i = 0; i < 6; i++) cfg_read(10'h020 + i, st[i]);
        $display("------------------------------------------------------------");
        $display(" frames in=%0d  verdicts=%0d  egress=%0d (expected %0d)", frames.size(), n_verd, n_out, fwd_idx.size());
        $display(" HW counters: committed=%0d dropped_ingress=%0d mal=%0d forwarded=%0d blocked=%0d",
                 st[0], st[1], st[2], st[3], st[4]);
        if (!STRESS)       // stress mode drops frames on purpose: no per-frame ground truth
            $display(" detection vs ground truth: TP=%0d FP=%0d TN=%0d FN=%0d  acc=%.4f",
                     tp, fp, tn, fn, real'(tp + tn) / real'(tp + tn + fp + fn));
        if (STRESS) begin
            if (st[0] + st[1] != frames.size()) begin errors++; $display("[ERR] committed+dropped != frames"); end
            if (st[3] + st[4] != st[0])         begin errors++; $display("[ERR] forwarded+blocked != committed"); end
            if (n_out != st[3])                 begin errors++; $display("[ERR] egress count != forwarded"); end
            if (st[1] == 0) $display("[WARN] stress test produced no ingress drops");
        end else begin
            if (st[1] != 0) begin errors++; $display("[ERR] unexpected ingress drops"); end
            if (st[2] != frames.size() - fwd_idx.size()) begin errors++; $display("[ERR] mal counter mismatch"); end
        end
        if (errors == 0 && STRESS) $display(" RESULT: PASS (stress/integrity)");
        else if (errors == 0)      $display(" RESULT: PASS (bit-exact with golden model)");
        else             $display(" RESULT: FAIL (%0d errors)", errors);
        $display("------------------------------------------------------------");
        $finish;
    end

endmodule
