#!/usr/bin/env python3
"""Measure polygons per guest frame from cumulative GP0 opcode counters,
correlating with the GP0 ring frame numbers."""
import collections
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630


def polys(port):
    r = send(port, '{"cmd":"gpu_opcodes"}')
    return sum(v for k, v in r.get("opcodes", {}).items()
               if 0x20 <= int(k, 16) <= 0x7F)


def frame(port):
    return send(port, '{"cmd":"frame"}')["frame"]


samples = []
t0 = time.perf_counter()
while time.perf_counter() - t0 < 1.0:
    samples.append((frame(PORT), polys(PORT)))

# aggregate polys per frame: use max-min within each frame observation
per = collections.defaultdict(list)
for f, p in samples:
    per[f].append(p)
rows = []
for f in sorted(per):
    if len(set(per[f])) > 1:
        rows.append((f, max(per[f]) - min(per[f])))
print("frame deltas (frame, polys-in-window):")
for f, d in rows[:20]:
    print("  %d: %d" % (f, d))
