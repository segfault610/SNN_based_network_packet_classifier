// ASIC top: snn_pkt_filter with ASIC-sized buffers. Flop-based memories for
// now (packet buffer 2 KiB x 9b, W1 64 x 128b); swap for foundry SRAM macros
// before tape-out.
module snn_pkt_filter_asic (
    input  wire        clk,
    input  wire        rst,
    input  wire [7:0]  s_axis_tdata,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,
    input  wire        s_axis_tuser,
    output wire [7:0]  m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast,
    output wire        m_axis_tuser,
    input  wire        cfg_wr,
    input  wire        cfg_rd,
    input  wire [9:0]  cfg_addr,
    input  wire [31:0] cfg_wdata,
    output wire [31:0] cfg_rdata,
    output wire        verdict_valid,
    output wire        verdict_mal
);
    snn_pkt_filter #(.BUF_AW(11)) u_filter (
        .clk(clk), .rst(rst),
        .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready),
        .s_axis_tlast(s_axis_tlast), .s_axis_tuser(s_axis_tuser),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready),
        .m_axis_tlast(m_axis_tlast), .m_axis_tuser(m_axis_tuser),
        .cfg_wr(cfg_wr), .cfg_rd(cfg_rd), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .cfg_rdata(cfg_rdata), .verdict_valid(verdict_valid), .verdict_mal(verdict_mal)
    );
endmodule
