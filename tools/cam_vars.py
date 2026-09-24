#!/usr/bin/env python3
"""Compare the two camera position sets the engine keeps.

Usage: python tools/cam_vars.py [--hold left|up|...] [--samples 12]
The sprite routines read X/Z/Y from 0x800775BC / C0 / D0; the sector loop hands
the terrain renderer 0x800775C8 / CC / D0. Prints both, the yaw byte and their
difference over time while a pad button is held.
"""
import json
import sys
import time

from ask import ask
from input_probe import BUTTONS

PORT = 4624


def q(**k):
    return ask(PORT, json.dumps(k), timeout=20.0, tries=2)


def words(addr, n):
    r = q(cmd="read_ram", addr="0x%08X" % addr, len=n * 4)
    raw = bytes.fromhex(r.get("hex") or r.get("data") or "")
    return [int.from_bytes(raw[i:i + 4], "little", signed=True) for i in range(0, len(raw) - 3, 4)]


def main():
    a = sys.argv[1:]
    n = int(a[a.index("--samples") + 1]) if "--samples" in a else 12
    mask = 0xFFFF
    if "--hold" in a:
        for b in a[a.index("--hold") + 1].split(","):
            mask &= ~BUTTONS[b]
    q(cmd="set_input", buttons=mask)
    time.sleep(0.5)
    for _ in range(n):
        w = words(0x800775B0, 12)          # B0 B4 B8 BC C0 C4 C8 CC D0 D4 D8 DC
        yaw = words(0x80077624, 1)[0] & 0xFF
        bc, c0, c4, c8, cc, d0 = w[3], w[4], w[5], w[6], w[7], w[8]
        print("yaw %3d | sprite cam (BC,C0)=(%7d,%7d) C4=%7d | terrain cam (C8,CC)=(%7d,%7d) D0=%6d | diff (%5d,%5d)" % (
            yaw, bc, c0, c4, c8, cc, d0, c8 - bc, cc - c0))
        time.sleep(0.25)
    q(cmd="clear_input")


if __name__ == "__main__":
    main()
