#!/usr/bin/env python3
"""Host cost of one engine pass, measured uncapped (headless diagnostics build).

Usage: python tools/pass_cost.py --slot N [--seconds 8] [--hold up,left]

Loads a savestate, optionally holds pad buttons, then measures over a wall
clock window: guest VBlanks delivered, render passes (screen clears) and from
those the host milliseconds per pass. Headless runs are uncapped, so
wall time / passes is the pure CPU cost of a pass in that view, independent of
the guest overclock (which only decides how many passes fit into a VBlank).
"""
import json
import sys
import time

from ask import ask
from input_probe import BUTTONS

PORT = 4624


def q(c, **k):
    d = {"cmd": c}
    d.update(k)
    return ask(PORT, json.dumps(d), timeout=20.0, tries=2)


def snap():
    return q("gpu_state")["gp0_fill"], q("vblank_rate")["delivered"], time.perf_counter()


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 8.0
    q("clear_input")
    q("savestate", op="load", slot=int(a[a.index("--slot") + 1]))
    time.sleep(3)
    if "--hold" in a:
        mask = 0xFFFF
        for b in a[a.index("--hold") + 1].split(","):
            mask &= ~BUTTONS[b]
        q("set_input", buttons=mask)
        time.sleep(1)
    f0, v0, t0 = snap()
    time.sleep(secs)
    f1, v1, t1 = snap()
    q("clear_input")
    passes, vbl, wall = f1 - f0, v1 - v0, t1 - t0
    print("passes/VBlank %.2f | guest %.0f Hz uncapped | host %.2f ms per pass | %.2f ms per VBlank"
          % (passes / max(1, vbl), vbl / wall, 1000.0 * wall / max(1, passes), 1000.0 * wall / max(1, vbl)))


if __name__ == "__main__":
    main()
