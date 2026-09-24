/* Fast guest timing for the recompiled GAME code (not the BIOS, not the
 * runtime, not the overlay shards). Force-included in front of every
 * generated/SLUS_002.24_full*.c by CMakeLists.txt when DISRUPTOR_FAST_TIMING
 * is non-zero; the generated files themselves are untouched.
 *
 * The framework's code generator brackets every recompiled instruction with a
 * Beetle-accurate timing model (pipeline give-back, load delay absorb,
 * instruction cache). That is what makes the framework cycle-exact, and it is
 * most of what the host CPU spends per guest instruction. This port runs the
 * guest CPU overclocked (runtime patch 010) precisely because Disruptor's
 * engine only needs "enough CPU per VBlank", so cycle exactness inside game
 * code buys nothing here. Devices, the BIOS and the kernel shards keep the
 * accurate model.
 *
 * Levels (cumulative), so each step can be measured with tools/pass_cost.py:
 *   1  per-block / per-function debug-server hooks compiled out of game code
 *   2  instruction cache simulation off for game code
 *   3  per-instruction timing replaced by one charge per basic block
 *      (the generator's own static instruction count for that block)
 *   4  main-RAM word/half loads read directly, with a flat cycle charge
 *   5  the per-branch interrupt check becomes an inline test; the runtime's
 *      full check (device service, IRQ delivery, idle skip, savestate and
 *      debug-server polls) runs only when it has something to do
 *
 * Function-like macros are used on purpose: the real declarations are parsed
 * first (include below), then only the call sites in generated code change. */
#ifndef DISRUPTOR_FAST_TIMING_H
#define DISRUPTOR_FAST_TIMING_H

#include "SLUS_002.24_decls.h"
#include <string.h>

#ifndef DISRUPTOR_FAST_TIMING
#define DISRUPTOR_FAST_TIMING 0
#endif

/* Guest cycles charged per load on top of the block's instruction count.
 * The accurate model charges 5-7 per main-RAM load and gives part of it back
 * on following instructions; this flat figure keeps the guest clock close to
 * the accurate build so the same DISRUPTOR_CPU_OVERCLOCK means the same thing. */
#ifndef DISRUPTOR_FAST_LOAD_CYCLES
#define DISRUPTOR_FAST_LOAD_CYCLES 2u
#endif

#if DISRUPTOR_FAST_TIMING >= 1
#ifdef __cplusplus
extern "C" {
#endif
extern volatile uint32_t g_psx_last_fn_entry;
#ifdef __cplusplus
}
#endif
#define debug_server_cyc_observe(addr) ((void)0)
#define debug_server_log_call_entry(addr) ((void)(g_psx_last_fn_entry = (addr)))
#endif

#if DISRUPTOR_FAST_TIMING >= 2
#define psx_icache_fetch(cpu, addr) ((void)0)
#endif

#if DISRUPTOR_FAST_TIMING >= 3 && defined(PSX_ENABLE_BLOCK_CYCLES)
#define psx_cyc_step(cpu, mask) ((void)0)
#define psx_slice_block(cpu, addr, bcyc, side_effects) (psx_cyc_charge(bcyc), 0)
#endif

#if DISRUPTOR_FAST_TIMING >= 4 && defined(PSX_ENABLE_BLOCK_CYCLES)
extern uint8_t *g_psx_ram;

static inline uint32_t disruptor_fast_load_word(CPUState* cpu, uint32_t addr,
                                                uint32_t rt, uint32_t reg_mask) {
    uint32_t phys = addr & 0x1FFFFFFFu;
    if (__builtin_expect(g_ls_mode == 0 && !g_ds_recording && phys < 0x00800000u, 1)) {
        uint32_t value;
        psx_cyc_charge(DISRUPTOR_FAST_LOAD_CYCLES);
        memcpy(&value, g_psx_ram + (phys & 0x1FFFFFu), sizeof(value));
        return value;
    }
    return psx_cyc_load_word_slow(cpu, addr, rt, reg_mask);
}

static inline uint16_t disruptor_fast_load_half(CPUState* cpu, uint32_t addr,
                                                uint32_t rt, uint32_t reg_mask) {
    uint32_t phys = addr & 0x1FFFFFFFu;
    if (__builtin_expect(g_ls_mode == 0 && !g_ds_recording && phys < 0x00800000u, 1)) {
        uint16_t value;
        psx_cyc_charge(DISRUPTOR_FAST_LOAD_CYCLES);
        memcpy(&value, g_psx_ram + (phys & 0x1FFFFFu), sizeof(value));
        return value;
    }
    return psx_cyc_load_half_slow(cpu, addr, rt, reg_mask);
}

#define psx_cyc_load_word(cpu, addr, rt, mask) disruptor_fast_load_word((cpu), (addr), (rt), (mask))
#define psx_cyc_load_half(cpu, addr, rt, mask) disruptor_fast_load_half((cpu), (addr), (rt), (mask))
#endif

#if DISRUPTOR_FAST_TIMING >= 5 && defined(PSX_ENABLE_BLOCK_CYCLES)
/* Host profile of a heavy view at level 4 (tools/host_profile.py): 29 % of the
 * game thread sat in the per-branch check (psx_check_interrupts,
 * psx_idle_note_check, psx_cyc_batch_flush and helpers) against ~3 % in the
 * recompiled game code itself.
 *
 * The full check is still made whenever it can matter:
 *   - an unmasked interrupt is pending;
 *   - DISRUPTOR_EDGE_CYCLES of CPU work have accumulated unpublished (bounds
 *     how late a device event or interrupt can be seen: 96 cycles at 300 %
 *     overclock is about one microsecond of guest time);
 *   - the same edge repeats back to back, i.e. a one-block polling loop such
 *     as the engine's VBlank wait. The idle skipper recognises those by
 *     seeing the same resume PC on consecutive checks, so they must keep
 *     reaching it every iteration.
 * MMIO accesses and GTE commands publish pending cycles themselves
 * (psx_devices_mmio_sync, psx_gte_*), so device-visible time stays exact. */
#ifndef DISRUPTOR_EDGE_CYCLES
#define DISRUPTOR_EDGE_CYCLES 96u
#endif
#ifdef __cplusplus
extern "C" {
#endif
extern uint32_t i_stat;
extern uint32_t i_mask;
extern uint32_t g_disruptor_edge_pc;
int savestate_pending(void);
void debug_server_poll(void);
#ifdef __cplusplus
}
#endif

static inline void disruptor_fast_edge(CPUState* cpu, uint32_t resume_pc) {
    uint32_t last = g_disruptor_edge_pc;
    g_disruptor_edge_pc = resume_pc;
    if (__builtin_expect(resume_pc != last && (i_stat & i_mask) == 0u &&
                         g_psx_cyc_batch < DISRUPTOR_EDGE_CYCLES, 1)) return;
    /* The runtime services a staged savestate save/load (F7/F8, debug port)
     * once per 16,384 full checks. Full checks are rare now, which stretched
     * that to several seconds (measured: a load still pending after 3 s in a
     * menu). While one is staged, drive the runtime's own check until its
     * maintenance step has taken it - about a millisecond, once. (Calling
     * savestate_poll directly from here was tried and made loads fail.) */
    /* Same for the debug port: its requests run on this thread from the
     * runtime's 1-in-16,384 maintenance step (measured ~3 s per request in a
     * paced window). Poll it every 256th full check: polling on every one cost
     * 3.4 ms per engine pass (9.7 -> 13.1 ms; the poll stamps a watchdog clock
     * and takes a mutex, ~17,000 times per VBlank). */
    {
        static unsigned s_poll_div;
        if ((++s_poll_div & 0xFFu) == 0u) debug_server_poll();
    }
    if (__builtin_expect(savestate_pending(), 0)) {
        for (int i = 0; i < 0x4000 && savestate_pending(); i++)
            (psx_check_interrupts_at)(cpu, resume_pc);
        return;
    }
    (psx_check_interrupts_at)(cpu, resume_pc);
}

#define psx_cyc_bb_defer_flush() ((void)0)
#define psx_check_interrupts_at(cpu, pc) disruptor_fast_edge((cpu), (pc))
#endif

#if defined(PSX_PGXP) && DISRUPTOR_FAST_TIMING >= 1
/* PGXP hook calls sit behind every load, store and ALU instruction. While the
 * engine is paused (no 3D on screen, disruptor_widescreen.c) skip the calls
 * themselves, not just their bodies. */
#ifdef __cplusplus
extern "C" {
#endif
extern int g_disruptor_pgxp_live;
#ifdef __cplusplus
}
#endif
#undef PGXP_LOAD
#undef PGXP_STORE
#undef PGXP_ALU
#undef PGXP_MULDIV
#undef PGXP_COP2
#define PGXP_LOAD(instr, addr, val)        ((void)(g_disruptor_pgxp_live ? (psx_pgxp_load(cpu, (instr), (addr), (val)), 0) : 0))
#define PGXP_STORE(instr, addr, val)       ((void)(g_disruptor_pgxp_live ? (psx_pgxp_store(cpu, (instr), (addr), (val)), 0) : 0))
#define PGXP_ALU(instr, res, s1, s2)       ((void)(g_disruptor_pgxp_live ? (psx_pgxp_alu(cpu, (instr), (res), (s1), (s2)), 0) : 0))
#define PGXP_MULDIV(instr, hi, lo, s1, s2) ((void)(g_disruptor_pgxp_live ? (psx_pgxp_muldiv(cpu, (instr), (hi), (lo), (s1), (s2)), 0) : 0))
#define PGXP_COP2(instr, val, addr)        ((void)(g_disruptor_pgxp_live ? (psx_pgxp_cop2(cpu, (instr), (val), (addr)), 0) : 0))
#endif

#endif /* DISRUPTOR_FAST_TIMING_H */
