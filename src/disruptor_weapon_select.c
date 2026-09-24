/*
 * Mouse-wheel weapon and psionic selection for Disruptor.
 *
 * The game selects through two lists (measured in the running game, weapon
 * and psionic selection): holding the weapon button (L1 by default; the game's
 * own control setup keeps its mask at gp+24) opens the weapon list, input
 * state gp+784 = 2; Down/Up step through the owned weapons, one step per
 * pressed edge; releasing the button selects. The psionic button (R1, mask
 * gp+28) does the same with the psionic list, state 3. A quick double tap of
 * a button instead swaps to the previously used weapon or power. While a list
 * is open the player does not move, so Up/Down only scroll.
 *
 * A wheel notch used to be a four-frame tap of L1/R1: it opened and closed the
 * list without scrolling it, and two notches in quick succession were a
 * double tap. This plugin claims the wheel and drives the game's own list
 * instead: it holds the list button until the list is open, sends one Down
 * (wheel down, next) or Up (wheel up, previous) edge per notch, keeps the list
 * open while notches keep coming and releases the button a moment after the
 * last one, which selects. Wheel alone scrolls the weapons; with the psionic
 * list open (psionic button held) it scrolls the psionics. Every step is
 * confirmed on the game's own button word, so a slow engine frame cannot
 * swallow one. DISRUPTOR_WHEEL_SELECT=0 hands the wheel back to keybinds.ini;
 * DISRUPTOR_WHEEL_LINGER=<frames> sets how long the list stays open after the
 * last notch (default 20, a third of a second).
 */
#include <stdint.h>
#include <stdlib.h>

#include "mod_plugins.h"
#include "psx_keybinds.h"

#define DWS_GP              0x8007114Cu
#define DWS_STATE           (DWS_GP + 784u)    /* u8: 0 play, 2 weapon list, 3 psionic list, 4 pause */
#define DWS_WEAPON_MASK     (DWS_GP + 24u)     /* u32: game-word bit of the weapon button */
#define DWS_PSI_MASK        (DWS_GP + 28u)     /* u32: game-word bit of the psionic button */
#define DWS_FRAME           (DWS_GP + 1452u)   /* u32: engine frame counter */
#define DWS_WEAPON_TAP      0x8007174Cu        /* u32: frame of the last weapon-button press */
#define DWS_PSI_TAP         0x80071348u        /* u32: frame of the last psionic-button press */
#define DWS_BUTTONS         0x80077670u        /* u32: buttons this engine frame (game layout) */

/* The game's button word is the pad word byte-swapped and active-high. */
#define DWS_G_UP            0x1000u
#define DWS_G_DOWN          0x4000u
#define DWS_P_UP            0x0010u            /* PSX pad bits, for injection */
#define DWS_P_DOWN          0x0040u

#define DWS_OPEN_FRAMES     45   /* wait this long for the list to open (a weapon change may be running) */
#define DWS_STEP_FRAMES     12   /* a step the game has not seen by then is dropped */
#define DWS_CLOSE_FRAMES    12

enum { DWS_IDLE, DWS_OPEN, DWS_LIFT, DWS_PRESS, DWS_LINGER, DWS_CLOSE };

static int s_enabled = -1;
static int s_linger = 20;          /* frames the list stays open after the last notch */
static int s_phase = DWS_IDLE;
static int s_list_state;           /* 2 weapons, 3 psionics */
static uint16_t s_list_button;     /* PSX pad bit of that list's button */
static int s_pending;              /* > 0: steps down (next), < 0: steps up (previous) */
static int s_carry;                /* steps that arrived while a list was closing */
static int s_timer;
static unsigned s_frames_since_3d = 1000u;

static uint16_t game_to_pad(uint32_t g) {
    return (uint16_t)(((g & 0xFFu) << 8) | ((g >> 8) & 0xFFu));
}

/* The press time the double tap compares against, pushed far back so a list
 * this plugin opens and closes never counts as the first or second tap. */
static void forget_tap(void) {
    const uint32_t now = psx_mod_read_word(DWS_FRAME);
    psx_mod_write_word(s_list_state == 3 ? DWS_PSI_TAP : DWS_WEAPON_TAP, now - 10000u);
}

static void finish(void) {
    if (s_phase != DWS_IDLE) forget_tap();
    psx_keybinds_set_mod_buttons(0, 0);
    s_phase = DWS_IDLE;
    s_pending = 0;
    s_timer = 0;
}

/* Called from the terrain renderer hook: 3D gameplay is on screen. */
void disruptor_wheel_select_note_3d(void) { s_frames_since_3d = 0u; }

static void disruptor_wheel_select_vblank(void) {
    if (s_enabled < 0) {
        const char *e = getenv("DISRUPTOR_WHEEL_SELECT");
        const char *l = getenv("DISRUPTOR_WHEEL_LINGER");
        s_enabled = (e && e[0] == '0') ? 0 : 1;
        if (l && l[0]) {
            const int v = atoi(l);
            if (v >= 2 && v <= 120) s_linger = v;
        }
        psx_keybinds_claim_wheel(s_enabled);
    }
    if (!s_enabled) return;
    const int notches = psx_keybinds_take_wheel_notches();
    if (s_frames_since_3d < 1000u) s_frames_since_3d++;
    /* Gameplay only (the 3D view drawn within the last few frames): menus never
     * see an injected button, and notches there are dropped. */
    if (!psx_mod_game_started() || s_frames_since_3d > 4u) {
        if (s_phase != DWS_IDLE) finish();
        return;
    }
    const int st = (int)psx_mod_read_byte(DWS_STATE);
    const uint32_t btn = psx_mod_read_word(DWS_BUTTONS);

    if (s_phase == DWS_IDLE) {
        const int steps = s_carry - notches;   /* wheel down (negative) = next = Down */
        s_carry = 0;
        if (steps == 0) return;
        if (st != 0 && st != 2 && st != 3) return;
        /* The psionic button held (list open, or about to): psionics. Were
         * none selectable, the list never opens and the notches are dropped,
         * rather than scrolling the weapons instead. */
        const uint32_t psi_game = psx_mod_read_word(DWS_PSI_MASK);
        s_list_state = (st == 3 || (st == 0 && (btn & psi_game))) ? 3 : 2;
        s_list_button = game_to_pad(psx_mod_read_word(s_list_state == 3 ? DWS_PSI_MASK
                                                                        : DWS_WEAPON_MASK));
        if (!s_list_button) return;
        s_pending = steps;
        s_timer = 0;
        if (st == s_list_state) {
            s_phase = DWS_LIFT;        /* the player holds the list open already */
        } else {
            forget_tap();
            s_phase = DWS_OPEN;
        }
    } else {
        s_pending -= notches;
    }

    uint16_t press = s_list_button, release = 0;
    switch (s_phase) {
    case DWS_OPEN:
        if (st == s_list_state) {
            s_phase = DWS_LIFT;
            s_timer = 0;
        } else if (++s_timer > DWS_OPEN_FRAMES || (st != 0 && st != s_list_state)) {
            finish();                  /* nothing to select, or the game is busy */
            return;
        }
        break;
    case DWS_LIFT:
    case DWS_PRESS:
    case DWS_LINGER:
        if (st != s_list_state) { finish(); return; }   /* the game closed the list */
        break;
    default:
        break;
    }

    const int down = s_pending > 0;
    const uint16_t dir_pad = down ? DWS_P_DOWN : DWS_P_UP;
    const uint32_t dir_game = down ? DWS_G_DOWN : DWS_G_UP;
    switch (s_phase) {
    case DWS_LIFT:                     /* a step needs the key up first (an edge) */
        if (s_pending == 0) { s_phase = DWS_LINGER; s_timer = 0; break; }
        release = DWS_P_UP | DWS_P_DOWN;
        if (!(btn & (DWS_G_UP | DWS_G_DOWN))) {
            s_phase = DWS_PRESS;
            s_timer = 0;
            release = 0;
            press |= dir_pad;
        } else if (++s_timer > DWS_STEP_FRAMES) {
            s_pending = 0;
        }
        break;
    case DWS_PRESS:
        press |= dir_pad;
        if (btn & dir_game) {          /* the game has seen this step */
            s_pending += down ? -1 : 1;
            s_phase = DWS_LIFT;
            s_timer = 0;
            press &= (uint16_t)~dir_pad;
            release = DWS_P_UP | DWS_P_DOWN;
        } else if (++s_timer > DWS_STEP_FRAMES) {
            s_pending = 0;
            s_phase = DWS_LINGER;
            s_timer = 0;
        }
        break;
    case DWS_LINGER:
        release = DWS_P_UP | DWS_P_DOWN;
        if (s_pending != 0) {
            s_phase = DWS_LIFT;
            s_timer = 0;
        } else if (++s_timer >= s_linger) {
            s_phase = DWS_CLOSE;       /* releasing the list button selects */
            s_timer = 0;
            press = 0;
            release = 0;
        }
        break;
    case DWS_CLOSE:
        press = 0;
        if (st != s_list_state || ++s_timer > DWS_CLOSE_FRAMES) {
            const int carry = s_pending;   /* notches during the close start a new list */
            finish();
            s_carry = carry;
            return;
        }
        break;
    default:
        break;
    }
    psx_keybinds_set_mod_buttons(press, release);
}

PSX_MOD_CONSTRUCTOR(disruptor_wheel_select_register) {
    (void)psx_mod_register_vblank_plugin("disruptor.wheel_select",
                                         disruptor_wheel_select_vblank);
}
