#!/usr/bin/env python3
"""Press pad buttons on the running game and/or save the presented frame.

Usage: python tools/shot.py [--press start,cross,down ...] [--hold FRAMES]
                            [--wait SECONDS] [--out logs/shot.png]
Each --press item is tapped in order with a short gap. The screenshot is the
composed window frame (aspect and widescreen margins included).
"""
import os
import sys
import time

from input_probe import BUTTONS, send

PORT = 4624


def main():
    a = sys.argv[1:]
    presses = a[a.index("--press") + 1].split(",") if "--press" in a else []
    hold = int(a[a.index("--hold") + 1]) if "--hold" in a else 4
    wait = float(a[a.index("--wait") + 1]) if "--wait" in a else 1.0
    out = a[a.index("--out") + 1] if "--out" in a else None
    for name in presses:
        mask = 0xFFFF
        for part in name.split("+"):
            mask &= ~BUTTONS[part]
        send(PORT, '{"cmd":"press","buttons":%d,"frames":%d}' % (mask, hold))
        time.sleep(0.45)
    time.sleep(wait)
    if out:
        path = os.path.abspath(out).replace("\\", "/")
        if os.path.exists(path):
            os.remove(path)
        send(PORT, '{"cmd":"present_shot","path":"%s"}' % path)
        for _ in range(40):
            if os.path.exists(path) and os.path.getsize(path) > 0:
                break
            time.sleep(0.1)
        print("saved" if os.path.exists(path) else "NOT saved", path)


if __name__ == "__main__":
    main()
