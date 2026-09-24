#!/usr/bin/env python3
"""Compare vblank delivery rate vs GTE ring frame-counter rate on a live
instance (headless free-run vs paced diagnostics)."""
import sys
import time

from input_probe import send

port = int(sys.argv[1]) if len(sys.argv) > 1 else 4625
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0


def vbl():
    return send(port, '{"cmd":"vblank_rate"}')["delivered"]


def ringframe():
    r = send(port, '{"cmd":"gte_ring_dump","count":1,"newest":1}')
    return r["entries"][-1]["frame"]


v0 = vbl()
f0 = ringframe()
t0 = time.perf_counter()
time.sleep(dur)
t1 = time.perf_counter()
v1 = vbl()
f1 = ringframe()
span = t1 - t0
print("span=%.2fs  vblanks +%d -> %.2f/s   ring frames +%d -> %.2f/s" %
      (span, v1 - v0, (v1 - v0) / span, f1 - f0, (f1 - f0) / span))
