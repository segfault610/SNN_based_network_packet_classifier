// Co-simulation back end for snn_test: the accelerator RTL (rtl/snn_lookaside_avmm.v) compiled
// with Verilator. hw_rd / hw_wr run real Avalon-MM cycles on it (read latency 1, as on the
// Chameleon96 LW bridge), so the exact same snn_test.c code is checked against the hardware
// description before it touches the board.   Build/run: ./run_cosim.sh
#include "Vsnn_lookaside_avmm.h"
#include "verilated.h"
#include "../hw.h"

static VerilatedContext   *ctx;
static Vsnn_lookaside_avmm *m;

static void tick() { m->clk = 0; m->eval(); ctx->timeInc(5); m->clk = 1; m->eval(); ctx->timeInc(5); }

extern "C" int hw_open(unsigned long)
{
	ctx = new VerilatedContext;
	m = new Vsnn_lookaside_avmm(ctx);
	m->avs_read = 0; m->avs_write = 0; m->avs_address = 0; m->avs_writedata = 0;
	m->reset = 1;
	for (int i = 0; i < 10; i++) tick();
	m->reset = 0;
	tick();
	return 0;
}

extern "C" uint32_t hw_rd(uint32_t word)
{
	m->avs_address = word; m->avs_read = 1;
	tick();                               // address sampled; VERDICT pops on this edge
	m->avs_read = 0; m->eval();
	uint32_t d = m->avs_readdata;         // read latency 1
	tick();
	return d;
}

extern "C" void hw_wr(uint32_t word, uint32_t value)
{
	m->avs_address = word; m->avs_writedata = value; m->avs_write = 1;
	tick();
	m->avs_write = 0;
	tick();
}

extern "C" const char *hw_name(void) { return "Verilator co-simulation of rtl/snn_lookaside_avmm.v"; }
