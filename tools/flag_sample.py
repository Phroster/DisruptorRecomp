#!/usr/bin/env python3
"""Sample candidate dispatcher flags rapidly; look for frame-parity alternation."""
import collections
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
seen = collections.Counter()
t0 = time.perf_counter()
n = 0
while time.perf_counter() - t0 < 3.0:
    r = send(PORT, '{"cmd":"read_ram","addr":"0x80071930","len":8}')
    raw = bytes.fromhex(r["hex"])
    a = int.from_bytes(raw[0:4], "little")
    b = int.from_bytes(raw[4:8], "little")
    seen[(a, b)] += 1
    n += 1
print("samples:", n)
for k, c in seen.most_common(10):
    print("  +0x0=0x%08X +0x4=0x%08X x%d" % (k[0], k[1], c))

seen2 = collections.Counter()
t0 = time.perf_counter()
while time.perf_counter() - t0 < 2.0:
    r = send(PORT, '{"cmd":"read_ram","addr":"0x800715EC","len":8}')
    raw = bytes.fromhex(r["hex"])
    a = int.from_bytes(raw[0:4], "little")
    b = int.from_bytes(raw[4:8], "little")
    seen2[(a, b)] += 1
print("second window (0x800715EC):")
for k, c in seen2.most_common(10):
    print("  +0x0=0x%08X +0x4=0x%08X x%d" % (k[0], k[1], c))
