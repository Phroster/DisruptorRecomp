#!/usr/bin/env python3
"""Pan the camera left/right with injected mouse motion (diagnostics build).

Usage: python tools/pan_inject.py [--seconds 40] [--speed 4] [--hold up]
Sends host_mouse dx at ~30 Hz, reversing direction every 2.5 s, optionally
holding pad buttons (e.g. strafing) so a measurement sees a moving picture.
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
    try:
        return ask(PORT, json.dumps(d), timeout=3.0, tries=1)
    except Exception:
        return None


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 40.0
    speed = int(a[a.index("--speed") + 1]) if "--speed" in a else 4
    if "--hold" in a:
        mask = 0xFFFF
        for b in a[a.index("--hold") + 1].split(","):
            mask &= ~BUTTONS[b]
        q("set_input", buttons=mask)
    t0 = time.time()
    while time.time() - t0 < secs:
        phase = int((time.time() - t0) / 2.5) % 2
        q("host_mouse", dx=speed if phase == 0 else -speed)
        time.sleep(1 / 30.0)
    q("clear_input")


if __name__ == "__main__":
    main()
