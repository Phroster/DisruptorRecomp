#!/usr/bin/env python3
"""Send relative mouse motion / wheel events to the foreground window.

Test aid for the runtime's relative-turn and wheel pseudo-bindings. Uses
SendInput through user32's mouse_event (works for any focused window).

Usage:
  python tools/mouse_wiggle.py move <dx_total> [--ms 8] [--step 12]
  python tools/mouse_wiggle.py wheel <notches>
"""
import argparse
import ctypes
import time

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_WHEEL = 0x0800


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["move", "wheel"])
    ap.add_argument("amount", type=int)
    ap.add_argument("--ms", type=int, default=8)
    ap.add_argument("--step", type=int, default=12)
    args = ap.parse_args()
    user32 = ctypes.windll.user32
    if args.kind == "move":
        remaining = args.amount
        while remaining != 0:
            step = args.step if remaining > 0 else -args.step
            if abs(step) > abs(remaining):
                step = remaining
            user32.mouse_event(MOUSEEVENTF_MOVE, step, 0, 0, 0)
            remaining -= step
            time.sleep(args.ms / 1000.0)
    else:
        for _ in range(abs(args.amount)):
            delta = 120 if args.amount > 0 else -120
            user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
            time.sleep(0.05)


if __name__ == "__main__":
    main()
