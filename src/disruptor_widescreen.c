/*
 * Game-owned presentation + input plugin for Disruptor.
 *
 *  - Widescreen (activation): fixed 16:9 host aspect (native-wide compositor),
 *    with real terrain in the side regions: see disruptor_terrain_window_hook.
 *    Presentation is one vsynced present per real 60 fps engine frame;
 *    temporal blending is opt-in (DISRUPTOR_INTERP_FPS).
 *
 *  - Mouse look (vblank + matrix hook): the game is yaw-only (the GTE
 *    projection center never moves and the camera matrix is a pure Y
 *    rotation). Yaw is a 1-byte angle index at 0x80077624 (1 unit = 1/256
 *    turn); the camera build at 0x80040F3C turns it into the Q12 rotation
 *    matrix and passes it to the GTE load at 0x8004FA60 with $a0 = &matrix.
 *    The vblank callback adds the mouse X delta to the yaw; the function
 *    entry hook composes a pitch (mouse Y) rotation into the matrix before
 *    the GTE consumes it, giving a modern full mouse look on an engine that
 *    only ever had horizontal aiming.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "mod_plugins.h"
#include "psx_keybinds.h"
#include "cpu_state.h"

#define DISRUPTOR_YAW_ADDR       0x80077624u
#define DISRUPTOR_MATRIX_LOADER  0x8004FA60u
#define DISRUPTOR_DEG_PER_PX_DEF 0.30f
#define DISRUPTOR_DEG_PER_PX_MAX 2.0f

/* Degrees per mouse count; override with DISRUPTOR_MOUSE_SENS without a
 * rebuild. Read once on the first vblank. */
static float s_deg_per_px = DISRUPTOR_DEG_PER_PX_DEF;
static int   s_deg_per_px_set = 0;

static float yaw_per_px(void) {
    if (!s_deg_per_px_set) {
        s_deg_per_px_set = 1;
        if (const char *e = getenv("DISRUPTOR_MOUSE_SENS")) {
            const float v = (float)atof(e);
            if (v > 0.0f && v <= DISRUPTOR_DEG_PER_PX_MAX) s_deg_per_px = v;
        }
    }
    return s_deg_per_px / (360.0f / 256.0f);
}

/* Camera pitch via matrix composition is DISABLED: rotating the world matrix
 * detaches the engine's ground sprites, which are positioned on a path that
 * assumes an unpitched camera. Re-enable only after the sprite projection
 * path is understood. */
#define DISRUPTOR_PITCH_ENABLE   0
#define DISRUPTOR_PITCH_MAX_DEG  75.0f
#define DISRUPTOR_TWO_PI         6.283185307179586f

static float s_pitch_deg = 0.0f;

static void disruptor_widescreen_activate(void) {
    (void)psx_mod_set_fixed_display_aspect(16u, 9u);
    /* Presentation: the engine now draws a real 60 fps (every guest frame is a
     * distinct picture), so temporal blending no longer adds motion - it only
     * cross-fades neighbouring frames (ghosting), forces driver vsync OFF
     * (tearing) and schedules presents on the emulation thread in the gap left
     * after each guest frame (uneven spacing = the residual stutter). Default
     * is therefore OFF: each guest frame is presented once, vsynced. On a
     * 120/180/240 Hz panel the runtime (patch 009) holds each frame for exactly
     * 2/3/4 refreshes; on a VRR (G-SYNC/FreeSync) panel the wall-clock pacer
     * drives an even 60 Hz. Opt back in with DISRUPTOR_INTERP_FPS=<60..240>
     * (or 0 = host refresh); DISRUPTOR_INTERP_BLEND=0 selects linear. */
    const char *fps_env = getenv("DISRUPTOR_INTERP_FPS");
    if (!fps_env || !fps_env[0]) return;
    const long v = atol(fps_env);
    if (v < 0 || v > 240 || (v > 0 && v < 60)) return;
    (void)psx_mod_set_frame_interpolation((uint32_t)v);
    uint32_t blend = (uint32_t)PSX_MOD_FRAME_INTERPOLATION_MOTION_ADAPTIVE;
    if (const char *e = getenv("DISRUPTOR_INTERP_BLEND")) {
        if (atoi(e) == 0) blend = (uint32_t)PSX_MOD_FRAME_INTERPOLATION_LINEAR;
    }
    (void)psx_mod_set_frame_interpolation_blend(blend);
}

/* Fractional yaw position across frames: the guest yaw is an integer 1/256-turn
 * byte, so rounding each frame's delta would discard slow mouse motion and
 * quantize everything else into 1.4-degree steps. Keep the fraction here, write
 * only the integer target, and resync whenever the game's own turn input (pad,
 * arrows) moved the yaw away from what we last wrote. */
static float s_yaw_pos = -1.0f;
static int   s_yaw_written = -1;

/* Sub-step view angle. The engine's yaw is one byte (256 steps per turn =
 * 1.41 degrees), so a slow mouse pan moves the whole view in jumps of ~8 px at
 * 320 px width (~35 px at 1440p) every few frames while strafing stays smooth:
 * that reads as stutter no matter how even the frame pacing is. Everything
 * that depends on the view direction - the camera matrix build, the portal
 * walk, the software-projected sprites, the player's movement vector - reads
 * sin/cos from two Q8 tables indexed by the yaw byte. So each guest frame the
 * slot for the current yaw is overwritten with the sin/cos of the fractional
 * angle (and the previous slot restored): every consumer sees the same,
 * smoother angle (Q8: ~0.2 degree steps). The camera matrix, the one Q12
 * consumer, is refined to full precision in disruptor_camera_matrix_hook.
 * DISRUPTOR_SMOOTH_YAW=0 turns all of it off. */
#define DISRUPTOR_SIN_TABLE      0x80057798u   /* s16[256], Q8 */
#define DISRUPTOR_COS_TABLE      0x80057998u   /* s16[256], Q8 */
#define DISRUPTOR_CAMERA_MTX_RA  0x80040FACu   /* return address of the camera-matrix load */
#define DISRUPTOR_RECIP_TABLE    0x80057E98u   /* u16[4096], floor(65536 / i) */
#define DISRUPTOR_SPRITE_CAM_X   0x800775BCu   /* camera x, z in whole units (sprites) */
#define DISRUPTOR_SPRITE_CAM_Z   0x800775C0u

static int      s_smooth_yaw = -1;
static int      s_tbl_idx = -1;                /* table slot currently overridden */
static uint16_t s_tbl_sin_orig, s_tbl_cos_orig;
static float    s_yaw_frac = 0.0f;             /* fractional yaw in table units, (-0.5, 0.5] */

static int smooth_yaw_enabled(void) {
    if (s_smooth_yaw < 0) {
        const char *e = getenv("DISRUPTOR_SMOOTH_YAW");
        s_smooth_yaw = (e && e[0] == '0') ? 0 : 1;
    }
    return s_smooth_yaw;
}

static void trig_slot_restore(void) {
    if (s_tbl_idx < 0) return;
    psx_mod_write_half(DISRUPTOR_SIN_TABLE + 2u * (uint32_t)s_tbl_idx, s_tbl_sin_orig);
    psx_mod_write_half(DISRUPTOR_COS_TABLE + 2u * (uint32_t)s_tbl_idx, s_tbl_cos_orig);
    s_tbl_idx = -1;
}

static void trig_slot_publish(int yaw, float frac) {
    trig_slot_restore();
    s_yaw_frac = 0.0f;
    if (!smooth_yaw_enabled() || (frac > -0.01f && frac < 0.01f)) return;
    const float theta = ((float)yaw + frac) * (DISRUPTOR_TWO_PI / 256.0f);
    s_tbl_idx = yaw & 0xFF;
    /* Remember the stock values to restore. They are read back from RAM, but a
     * savestate taken while a slot was overridden would make that override
     * look stock, so a value more than 1 LSB away from round(256*sin/cos) -
     * the tables match that formula to within 1 - is replaced by the formula. */
    {
        const float t0 = (float)s_tbl_idx * (DISRUPTOR_TWO_PI / 256.0f);
        const float s0 = sinf(t0) * 256.0f, c0 = cosf(t0) * 256.0f;
        const int sm = (int)(s0 + (s0 >= 0.0f ? 0.5f : -0.5f));
        const int cm = (int)(c0 + (c0 >= 0.0f ? 0.5f : -0.5f));
        int sr = (int)(int16_t)psx_mod_read_half(DISRUPTOR_SIN_TABLE + 2u * (uint32_t)s_tbl_idx);
        int cr = (int)(int16_t)psx_mod_read_half(DISRUPTOR_COS_TABLE + 2u * (uint32_t)s_tbl_idx);
        if (sr - sm > 1 || sm - sr > 1) sr = sm;
        if (cr - cm > 1 || cm - cr > 1) cr = cm;
        s_tbl_sin_orig = (uint16_t)(int16_t)sr;
        s_tbl_cos_orig = (uint16_t)(int16_t)cr;
    }
    const float sv = sinf(theta) * 256.0f, cv = cosf(theta) * 256.0f;
    psx_mod_write_half(DISRUPTOR_SIN_TABLE + 2u * (uint32_t)s_tbl_idx,
                       (uint16_t)(int16_t)(sv + (sv >= 0.0f ? 0.5f : -0.5f)));
    psx_mod_write_half(DISRUPTOR_COS_TABLE + 2u * (uint32_t)s_tbl_idx,
                       (uint16_t)(int16_t)(cv + (cv >= 0.0f ? 0.5f : -0.5f)));
    s_yaw_frac = frac;
}

/* Per-frame motion log (diagnostic, off unless DISRUPTOR_MOTION_LOG=<file>).
 * One CSV row per guest frame: host time in microseconds, the render camera
 * position the sector loop hands to the terrain renderer (0x800775C8/CC/D0),
 * the yaw byte and the published sub-step fraction. Written from the game's
 * own frame callback, so it works on the lean build and perturbs nothing;
 * analyse with tools/motion_log_report.py. */
#define DISRUPTOR_CAM_POS 0x800775C8u
static void motion_log_frame(void) {
    static int state = 0;               /* 0 = unchecked, 1 = logging, -1 = off */
    static FILE *fp = NULL;
    static unsigned long frame = 0;
    if (state == 0) {
        const char *path = getenv("DISRUPTOR_MOTION_LOG");
        fp = (path && path[0]) ? fopen(path, "w") : NULL;
        state = fp ? 1 : -1;
        if (fp) fprintf(fp, "frame,host_us,x,y,z,yaw,yaw_frac\n");
    }
    if (state != 1) return;
    struct timespec ts;
    timespec_get(&ts, TIME_UTC);
    const long long us = (long long)ts.tv_sec * 1000000LL + ts.tv_nsec / 1000;
    fprintf(fp, "%lu,%lld,%d,%d,%d,%u,%.3f\n", frame++, us,
            (int)psx_mod_read_word(DISRUPTOR_CAM_POS),
            (int)psx_mod_read_word(DISRUPTOR_CAM_POS + 4u),
            (int)psx_mod_read_word(DISRUPTOR_CAM_POS + 8u),
            (unsigned)psx_mod_read_byte(DISRUPTOR_YAW_ADDR), (double)s_yaw_frac);
    if ((frame & 63u) == 0u) fflush(fp);
}

/* PGXP bookkeeping runs on every load, store and ALU instruction of the game
 * code, also while nothing 3D is on screen (intro videos, menus). Measured on
 * the intro, headless diagnostics build, uncapped: 63 guest Hz with it, 72+
 * without. The engine only matters while the game projects geometry, so it is
 * paused when neither of the engine's per-frame 3D entry points (camera matrix
 * load 0x8004FA60, terrain renderer 0x80046134 - both already hooked below)
 * has run for half a second, and resumed by the first call of either.
 * Paused = the framework's counted suppression bracket plus
 * g_disruptor_pgxp_live = 0, which src/disruptor_fast_timing.h tests inline in
 * front of every PGXP hook call in the game code. Shadows are dropped on
 * resume; the engine validates every value on use anyway.
 * DISRUPTOR_PGXP_AUTOPAUSE=0 keeps it running always. */
#ifdef __cplusplus
extern "C" {
#endif
extern int g_disruptor_pgxp_live;
#ifdef __cplusplus
}
#endif
#ifdef PSX_PGXP
#include "pgxp.h"
static int s_pgxp_autopause = -1, s_pgxp_paused = 0, s_pgxp_idle_frames = 0;

static void disruptor_pgxp_note_3d(void) {
    s_pgxp_idle_frames = 0;
    if (s_pgxp_paused) {
        s_pgxp_paused = 0;
        g_disruptor_pgxp_live = 1;
        pgxp_suppress_end();
        pgxp_invalidate_all();
    }
}

static void disruptor_pgxp_autopause_vblank(void) {
    if (s_pgxp_autopause < 0) {
        const char *e = getenv("DISRUPTOR_PGXP_AUTOPAUSE");
        s_pgxp_autopause = (e && e[0] == '0') ? 0 : 1;
    }
    if (!s_pgxp_autopause || s_pgxp_paused) return;
    if (++s_pgxp_idle_frames >= 30) {
        pgxp_suppress_begin();
        g_disruptor_pgxp_live = 0;
        s_pgxp_paused = 1;
    }
}
#else
static void disruptor_pgxp_note_3d(void) {}
static void disruptor_pgxp_autopause_vblank(void) {}
#endif

/* Guest frame boundary: apply the horizontal mouse motion to the yaw byte. */
static void disruptor_mouselook_vblank(void) {
    disruptor_pgxp_autopause_vblank();
    if (!psx_mod_game_started()) return;
    motion_log_frame();
    const float dx = psx_keybinds_take_mouse_dx();
    const int game_yaw = (int)psx_mod_read_byte(DISRUPTOR_YAW_ADDR);
    if (s_yaw_pos < 0.0f || game_yaw != s_yaw_written) {
        s_yaw_pos = (float)game_yaw;   /* first call, or the game turned */
    }
    if (dx != 0.0f) {
        s_yaw_pos -= dx * yaw_per_px();
        while (s_yaw_pos < 0.0f)    s_yaw_pos += 256.0f;
        while (s_yaw_pos >= 256.0f) s_yaw_pos -= 256.0f;
    }
    const int out = ((int)(s_yaw_pos + 0.5f)) & 0xFF;
    /* Record the target even when it matches the byte, or the next frame would
     * resync away the sub-unit fraction. */
    s_yaw_written = out;
    if (out != game_yaw) psx_mod_write_byte(DISRUPTOR_YAW_ADDR, (uint8_t)out);
    float frac = s_yaw_pos - (float)out;
    if (frac > 128.0f)  frac -= 256.0f;   /* rounding wrapped 255.6 -> 0 */
    if (frac < -128.0f) frac += 256.0f;
    trig_slot_publish(out, frac);
#ifdef PSX_PGXP
    /* The engine projects its sprites (bodies, pickups, enemies) on the CPU with
     * these Q8 tables, >> 8 and integer divides (func_8003B78C and its three
     * siblings), which lands them on whole pixels up to ~1 px away from where the
     * GTE-projected world puts the same spot: they dance against the ground when
     * the view moves. PGXP's scalar tier carries the unrounded values through
     * that maths; it needs the exact sine/cosine behind a table entry, including
     * the sub-step angle published in the current slot. */
    pgxp_set_trig_tables(DISRUPTOR_SIN_TABLE, DISRUPTOR_COS_TABLE, 256u, 256.0,
                         out, (double)s_yaw_frac);
    /* Sprite sizes come from a reciprocal table indexed by depth
     * (w = W * 160 * recip[z] >> 16, 4096 entries of floor(65536 / i)): whole
     * pixel sizes, and the centred sprite hops half a pixel at every step. */
    pgxp_set_recip_table(DISRUPTOR_RECIP_TABLE, 4096u, 65536.0);
    /* They also use the camera position in whole units (0x800775BC/C0) while
     * the terrain uses it in eighths (0x800775C8/CC): walking moved every
     * sprite in steps of up to a unit against the ground (1.6 px at 100 units). */
    pgxp_set_word_alias(0, DISRUPTOR_SPRITE_CAM_X, DISRUPTOR_CAM_POS, 3u, psx_mod_read_word);
    pgxp_set_word_alias(1, DISRUPTOR_SPRITE_CAM_Z, DISRUPTOR_CAM_POS + 4u, 3u, psx_mod_read_word);
#endif
}

static void put_half(uint32_t addr, float value_q12) {
    int32_t v = (int32_t)(value_q12 + (value_q12 >= 0.0f ? 0.5f : -0.5f));
    if (v > 32767) v = 32767;
    if (v < -32768) v = -32768;
    psx_mod_write_half(addr, (uint16_t)(int16_t)v);
}

/* GTE rotation-matrix load entry: $a0 holds the matrix the camera build just
 * produced. Compose the pitch rotation onto it when the mouse has moved
 * vertically; with no pitch we leave the game's matrix untouched. */
static void disruptor_pitch_hook(struct CPUState* cpu, uint32_t address) {
    disruptor_pgxp_note_3d();
    (void)address;
    /* Camera matrix only (this loader also serves object matrices): rebuild
     * the yaw rotation at full Q12 precision for the fractional angle the
     * vblank callback published. Layout: [cos 0 sin; 0 1 0; -sin 0 cos]. */
    if (s_yaw_frac != 0.0f && cpu->gpr[31] == DISRUPTOR_CAMERA_MTX_RA &&
        psx_mod_game_started() &&
        (int)psx_mod_read_byte(DISRUPTOR_YAW_ADDR) == s_tbl_idx) {
        const uint32_t m = cpu->gpr[4];
        const float th = ((float)s_tbl_idx + s_yaw_frac) * (DISRUPTOR_TWO_PI / 256.0f);
        const float cq = cosf(th) * 4096.0f, sq = sinf(th) * 4096.0f;
        put_half(m + 0,  cq);
        put_half(m + 4,  sq);
        put_half(m + 12, -sq);
        put_half(m + 16, cq);
    }
#if !DISRUPTOR_PITCH_ENABLE
    return;
#else
    if (!psx_mod_game_started()) return;

    const float dy = psx_keybinds_take_mouse_dy();
    if (dy > -1.0f && dy < 1.0f) {
        if (dy != 0.0f) psx_keybinds_mouse_motion_y(dy);
    } else {
        /* SDL yrel is positive downward; positive pitch is looking up. */
        s_pitch_deg += dy * s_deg_per_px;
        if (s_pitch_deg > DISRUPTOR_PITCH_MAX_DEG)
            s_pitch_deg = DISRUPTOR_PITCH_MAX_DEG;
        if (s_pitch_deg < -DISRUPTOR_PITCH_MAX_DEG)
            s_pitch_deg = -DISRUPTOR_PITCH_MAX_DEG;
    }
    if (s_pitch_deg == 0.0f) return;

    const uint32_t mtx = cpu->gpr[4];
    const float theta = (float)psx_mod_read_byte(DISRUPTOR_YAW_ADDR) *
                        (DISRUPTOR_TWO_PI / 256.0f);
    const float pitch = s_pitch_deg * (DISRUPTOR_TWO_PI / 360.0f);
    const float c = cosf(theta), s = sinf(theta);
    const float cp = cosf(pitch), sp = sinf(pitch);

    /* Rx(pitch) * Ry(yaw), Q12, row-vector convention (matches the game's
     * [cos,0,sin; 0,1,0; -sin,0,cos] layout). */
    put_half(mtx + 0,  c * 4096.0f);
    put_half(mtx + 2,  0.0f);
    put_half(mtx + 4,  s * 4096.0f);
    put_half(mtx + 6,  sp * s * 4096.0f);
    put_half(mtx + 8,  cp * 4096.0f);
    put_half(mtx + 10, -sp * c * 4096.0f);
    put_half(mtx + 12, -cp * s * 4096.0f);
    put_half(mtx + 14, sp * 4096.0f);
    put_half(mtx + 16, cp * c * 4096.0f);
#endif
}

/* True 16:9 terrain. The engine is a portal renderer: every sector is drawn
 * through a screen-space x window {xmin, xmax} that the terrain renderer
 * (func_80046134, $a1 -> {camx, camy, camz, xmin, xmax}) uses to drop polygons
 * lying entirely outside it. Stock, every window is clamped to the 4:3 screen
 * [0, 320], so no world geometry exists in the 16:9 side regions. game.toml's
 * "ws-*" patches make the portal pass compute its windows in coordinates
 * biased by +64 px over the range [0, 448] (constants only); this hook removes
 * the bias as the renderer is entered, so the real windows span [-64, 384]
 * and the engine submits genuine terrain for the whole 16:9 view (-53..373).
 * The hook must run exactly once per guest call: that holds because the entry
 * block is never re-entered (the framework's precise block slicing, the only
 * thing that re-dispatches a block leader, is parked off: PSX_PRECISE_SLICE). */
#define DISRUPTOR_TERRAIN_RENDER   0x80046134u
#define DISRUPTOR_WINDOW_BIAS      64

void disruptor_wheel_select_note_3d(void);   /* src/disruptor_weapon_select.c */

static void disruptor_terrain_window_hook(struct CPUState* cpu, uint32_t address) {
    disruptor_pgxp_note_3d();
    disruptor_wheel_select_note_3d();
    (void)address;
    const uint32_t args = cpu->gpr[5];
    const int32_t xmin = (int32_t)psx_mod_read_word(args + 0x0Cu);
    const int32_t xmax = (int32_t)psx_mod_read_word(args + 0x10u);
    /* Only values the biased portal pass can produce; anything else is left
     * alone so an unexpected caller cannot be corrupted. */
    if (xmin < 0 || xmin > 320 + 2 * DISRUPTOR_WINDOW_BIAS ||
        xmax < 0 || xmax > 320 + 2 * DISRUPTOR_WINDOW_BIAS)
        return;
    psx_mod_write_word(args + 0x0Cu, (uint32_t)(xmin - DISRUPTOR_WINDOW_BIAS));
    psx_mod_write_word(args + 0x10u, (uint32_t)(xmax - DISRUPTOR_WINDOW_BIAS));
}

PSX_MOD_CONSTRUCTOR(disruptor_register_plugins) {
    (void)psx_mod_register_activation_plugin("disruptor.widescreen",
                                             disruptor_widescreen_activate);
    (void)psx_mod_register_vblank_plugin("disruptor.mouselook",
                                         disruptor_mouselook_vblank);
    (void)psx_mod_register_function_entry_plugin(
        "disruptor.mouselook", DISRUPTOR_MATRIX_LOADER, disruptor_pitch_hook);
    (void)psx_mod_register_function_entry_plugin(
        "disruptor.widescreen", DISRUPTOR_TERRAIN_RENDER,
        disruptor_terrain_window_hook);
}
