/* State for src/disruptor_fast_timing.h (fast guest timing of game code). */
#include <stdint.h>

/* Resume PC of the last basic-block edge taken in recompiled game code. */
uint32_t g_disruptor_edge_pc = 0;

/* 0 while the PGXP engine is paused (no 3D on screen); see
 * disruptor_pgxp_autopause_vblank in disruptor_widescreen.c. */
int g_disruptor_pgxp_live = 1;
