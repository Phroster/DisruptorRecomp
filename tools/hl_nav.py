#!/usr/bin/env python3
"""Headless navigation helper: tap buttons, then save the guest display.

Usage: python tools/hl_nav.py [--press a,b+c,...] [--hold N] [--wait S] [--out file.png]
Works without a window (uses the runtime's VRAM-side screenshot_file).
"""
import json
import os
import sys
import time

from ask import ask
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
        time.sleep(0.5)
    time.sleep(wait)
    if out:
        path = os.path.abspath(out).replace(os.sep, "/")
        if os.path.exists(path):
            os.remove(path)
        r = ask(PORT, json.dumps({"cmd": "screenshot_file", "path": path}), timeout=15.0, tries=1)
        for _ in range(30):
            if os.path.exists(path) and os.path.getsize(path) > 0:
                break
            time.sleep(0.1)
        print("saved" if os.path.exists(path) else "NOT saved: %s" % json.dumps(r)[:200], path)


if __name__ == "__main__":
    main()
