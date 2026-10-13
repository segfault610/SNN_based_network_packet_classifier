// System-level test: GMII PHY bytes -> verilog-ethernet eth_mac_1g (preamble/FCS
// check+strip) -> snn_pkt_filter -> RX async frame FIFO -> host AXI-Stream.
// Same vectors as tb_snn_pkt_filter; verdicts and host-visible frames checked.
`timescale 1ns/1ps
module tb_eth_mac_snn;
    parameter string VEC_DIR = "vectors";

    logic clk = 0, rst = 1;
    always #4 clk = ~clk;                      // 125 MHz GMII rx_clk / logic_clk

    logic [7:0] gmii_rxd = 0; logic gmii_rx_dv = 0, gmii_rx_er = 0;
    logic [7:0] rx_tdata; logic rx_tvalid, rx_tready, rx_tlast, rx_tuser;
    logic        cfg_wr = 0, cfg_rd = 0; logic [9:0] cfg_addr = 0;
    logic [31:0] cfg_wdata = 0, cfg_rdata;

    eth_mac_1g_snn_fifo #(.ENABLE_PADDING(1), .MIN_FRAME_LENGTH(64)) dut (
        .rx_clk(clk), .rx_rst(rst), .tx_clk(clk), .tx_rst(rst), .logic_clk(clk), .logic_rst(rst),
        .tx_axis_tdata(8'd0), .tx_axis_tkeep(1'b1), .tx_axis_tvalid(1'b0), .tx_axis_tready(),
        .tx_axis_tlast(1'b0), .tx_axis_tuser(1'b0),
        .rx_axis_tdata(rx_tdata), .rx_axis_tkeep(), .rx_axis_tvalid(rx_tvalid), .rx_axis_tready(rx_tready),
        .rx_axis_tlast(rx_tlast), .rx_axis_tuser(rx_tuser),
        .gmii_rxd(gmii_rxd), .gmii_rx_dv(gmii_rx_dv), .gmii_rx_er(gmii_rx_er),
        .gmii_txd(), .gmii_tx_en(), .gmii_tx_er(),
        .rx_clk_enable(1'b1), .tx_clk_enable(1'b1), .rx_mii_select(1'b0), .tx_mii_select(1'b0),
        .tx_error_underflow(), .tx_fifo_overflow(), .tx_fifo_bad_frame(), .tx_fifo_good_frame(),
        .rx_error_bad_frame(), .rx_error_bad_fcs(), .rx_fifo_overflow(), .rx_fifo_bad_frame(),
        .rx_fifo_good_frame(), .cfg_ifg(8'd12), .cfg_tx_enable(1'b1), .cfg_rx_enable(1'b1),
        .snn_cfg_wr(cfg_wr), .snn_cfg_rd(cfg_rd), .snn_cfg_addr(cfg_addr), .snn_cfg_wdata(cfg_wdata),
        .snn_cfg_rdata(cfg_rdata), .snn_verdict_valid(), .snn_verdict_mal()
    );

    typedef byte unsigned frame_t[$];
    frame_t frames[$];
    int exp_mal[$], exp_lab[$], fwd_idx[$];
    int errors = 0, n_out = 0, n_verd = 0;

    function automatic logic [31:0] crc32(frame_t f);
        logic [31:0] c = 32'hFFFF_FFFF;
        foreach (f[i]) begin
            c ^= f[i];
            repeat (8) c = c[0] ? (c >> 1) ^ 32'hEDB8_8320 : (c >> 1);
        end
        return ~c;
    endfunction

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
            exp_mal.push_back(mal); exp_lab.push_back(lab);
        end
        $fclose(fd);
        foreach (exp_mal[i]) if (!exp_mal[i]) fwd_idx.push_back(i);
    endtask

    task automatic cfg_write(input logic [9:0] a, input logic [31:0] d);
        @(posedge clk); cfg_wr <= 1; cfg_addr <= a; cfg_wdata <= d;
        @(posedge clk); cfg_wr <= 0;
    endtask

    task automatic gmii_send(frame_t f);
        logic [31:0] fcs = crc32(f);
        frame_t w = {8'h55, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, 8'hD5};
        w = {w, f, fcs[7:0], fcs[15:8], fcs[23:16], fcs[31:24]};
        foreach (w[i]) begin @(posedge clk); gmii_rx_dv <= 1; gmii_rxd <= w[i]; end
        @(posedge clk); gmii_rx_dv <= 0; gmii_rxd <= 0;
        repeat ($urandom_range(30, 11)) @(posedge clk);     // >= 12-byte IFG
    endtask

    always @(posedge clk) rx_tready <= ($urandom_range(99, 0) < 90);

    always @(posedge clk) if (!rst && dut.snn_filter_inst.verd_push) begin
        if (dut.snn_filter_inst.c_mal !== exp_mal[n_verd][0]) begin
            errors++; $display("[ERR] verdict %0d mismatch", n_verd);
        end
        n_verd++;
    end

    frame_t rx;
    always @(posedge clk) if (!rst && rx_tvalid && rx_tready) begin
        rx.push_back(rx_tdata);
        if (rx_tlast) begin
            if (rx_tuser) begin errors++; $display("[ERR] host got frame with tuser=1"); end
            if (n_out >= fwd_idx.size() || rx != frames[fwd_idx[n_out]]) begin
                errors++; $display("[ERR] host frame %0d mismatch (%0d bytes)", n_out, rx.size());
            end
            n_out++; rx = {};
        end
    end

    initial begin
        int fd, a, d;
        load();
        repeat (10) @(posedge clk); rst <= 0; repeat (10) @(posedge clk);
        fd = $fopen({VEC_DIR, "/cfg.txt"}, "r");
        while ($fscanf(fd, "%h %h", a, d) == 2) cfg_write(a[9:0], d);
        $fclose(fd);
        foreach (frames[i]) gmii_send(frames[i]);
        fork
            wait (n_out == fwd_idx.size());
            begin repeat (100000) @(posedge clk); errors++; $display("[ERR] timeout"); end
        join_any
        disable fork;
        $display("------------------------------------------------------------");
        $display(" GMII frames sent=%0d  SNN verdicts=%0d  host frames=%0d (expected %0d), blocked=%0d",
                 frames.size(), n_verd, n_out, fwd_idx.size(), frames.size() - fwd_idx.size());
        if (errors == 0 && n_verd == frames.size()) $display(" RESULT: PASS (MAC + SNN firewall integration)");
        else $display(" RESULT: FAIL (%0d errors)", errors);
        $display("------------------------------------------------------------");
        $finish;
    end
endmodule
