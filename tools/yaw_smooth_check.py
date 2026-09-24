#!/usr/bin/env python3
"""Check the mod's sub-step view angle against the live game (headless works).

Usage: python tools/yaw_smooth_check.py [--slot N]   (loads savestate N first)

Injects 1-pixel mouse motions and prints, per step, the engine's yaw byte, the
sin/cos the engine will read from its tables for that yaw, the stock values,
and the angle those table values imply. With DISRUPTOR_SMOOTH_YAW on, the
implied angle should advance in small even steps between yaw-byte changes.
"""
import json
import math
import struct
import sys
import time

from ask import ask

PORT = 4624
SIN, COS, YAW = 0x80057798, 0x80057998, 0x80077624


def q(c, **k):
    d = {"cmd": c}
    d.update(k)
    return ask(PORT, json.dumps(d), timeout=20.0, tries=2)


def peek(addr, n):
    return bytes.fromhex(q("read_ram", addr="0x%08X" % addr, len=n)["hex"])


def main():
    a = sys.argv[1:]
    if "--slot" in a:
        print(q("savestate", op="load", slot=int(a[a.index("--slot") + 1])))
        time.sleep(4)
    print("step | yaw | table sin,cos | stock sin,cos | implied angle (yaw units)")
    for step in range(16):
        q("host_mouse", dx=1)
        time.sleep(0.12)
        yaw = peek(YAW, 1)[0]
        s = struct.unpack("<h", peek(SIN + 2 * yaw, 2))[0]
        c = struct.unpack("<h", peek(COS + 2 * yaw, 2))[0]
        ss = round(math.sin(yaw * 2 * math.pi / 256) * 256)
        cs = round(math.cos(yaw * 2 * math.pi / 256) * 256)
        ang = (math.atan2(s, c) * 256 / (2 * math.pi)) % 256
        print("%4d | %3d | %5d,%5d | %5d,%5d | %.2f" % (step, yaw, s, c, ss, cs, ang))


if __name__ == "__main__":
    main()
