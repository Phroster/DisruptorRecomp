#!/usr/bin/env python3
"""Dump all registers and sample GP-relative engine globals rapidly."""
import json
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630

r = send(PORT, '{"cmd":"get_registers"}')
gpr = r.get("gpr")
print("pc:", r.get("pc"), "frame:", r.get("frame"))
print("gpr type:", type(gpr), "len:", len(gpr) if gpr else None)
for i, v in enumerate(gpr):
    print("  r%-2d = %s" % (i, v))
gp = gpr[28]
gp = int(gp, 16) if isinstance(gp, str) else int(gp)
print("gp = 0x%08X" % gp)
print("gp+520  = 0x%08X" % (gp + 520))
print("gp+1188 = 0x%08X" % (gp + 1188))

A = gp + 520
B = gp + 1188
rows = []
t0 = time.perf_counter()
while time.perf_counter() - t0 < 2.0:
    v = send(PORT, '{"cmd":"read_ram","addr":"0x%X","len":8}' % A)["hex"]
    raw = bytes.fromhex(v)
    rows.append((raw[0], int.from_bytes(raw[4:8], "little")))
seen = {}
for a, b in rows:
    seen.setdefault((a, b), 0)
    seen[(a, b)] += 1
print("samples:", len(rows), "distinct (byte@+520, word@+1188) values:")
for k, n in sorted(seen.items(), key=lambda kv: -kv[1])[:12]:
    print("   %s x%d" % (k, n))
