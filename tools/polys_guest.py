#!/usr/bin/env python3
"""Polygons per guest-second (real draw-rate measure), plus 0x5A860 write
counts per frame from two recorded frames to see the loop's sync completions."""
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
CYCLES = 33868800.0
VBL = 564480


def polys(port):
    r = send(port, '{"cmd":"gpu_opcodes"}')
    return sum(v for k, v in r.get("opcodes", {}).items()
               if 0x20 <= int(k, 16) <= 0x7F)


def vbl(port):
    return send(port, '{"cmd":"vblank_rate"}')["delivered"]


p0, v0 = polys(PORT), vbl(PORT)
t0 = time.perf_counter()
time.sleep(6.0)
dt = time.perf_counter() - t0
p1, v1 = polys(PORT), vbl(PORT)
guest = (v1 - v0) * VBL / CYCLES
print("wall=%.2fs guest=%.2fs (%.2fx) polys +%d -> %.0f/guest-s (wall %.0f/s)"
      % (dt, guest, guest / dt, p1 - p0, (p1 - p0) / guest, (p1 - p0) / dt))
