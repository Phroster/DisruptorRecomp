#!/usr/bin/env python3
"""Sample the loop's frame-sync variable 0x8005A860: consecutive distinct
values tell how many counter ticks pass per game-loop iteration."""
import collections
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
vals = []
t0 = time.perf_counter()
while time.perf_counter() - t0 < 3.0:
    r = send(PORT, '{"cmd":"read_ram","addr":"0x5A860","len":4}')
    v = int.from_bytes(bytes.fromhex(r["hex"]), "little")
    if not vals or vals[-1] != v:
        vals.append(v)
print("samples:", len(vals))
deltas = collections.Counter()
for a, b in zip(vals, vals[1:]):
    deltas[b - a] += 1
print("value deltas between consecutive observed updates:", deltas.most_common(8))
print("first values:", ["0x%X" % v for v in vals[:12]])
