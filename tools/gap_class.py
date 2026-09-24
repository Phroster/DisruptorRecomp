#!/usr/bin/env python3
"""Classify each uncovered text gap: data (strings/zeros/pointers) vs code-like.

Usage: python tools/gap_class.py
"""
import re

LO, HI = 0x80010000, 0x80071800
exe = open("input/SLUS_002.24", "rb").read()

ivals = []
for line in open("generated/SLUS_002.24_full.ranges", encoding="utf-8",
                 errors="replace"):
    m = re.match(r"^R\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]+)\s*$", line.strip())
    if m:
        ivals.append((int(m.group(1), 16), int(m.group(1), 16) + int(m.group(2), 16)))
ivals.sort()
merged = []
for lo, hi in ivals:
    if merged and lo <= merged[-1][1]:
        merged[-1][1] = max(merged[-1][1], hi)
    else:
        merged.append([lo, hi])

gaps = []
cur = LO
for lo, hi in merged:
    if hi <= LO or lo >= HI:
        continue
    lo, hi = max(lo, LO), min(hi, HI)
    if lo > cur:
        gaps.append((cur, lo - cur))
    cur = max(cur, hi)
if cur < HI:
    gaps.append((cur, HI - cur))


def rd(va, n):
    off = 0x800 + (va - LO)
    return exe[off:off + n]


for lo, ln in gaps:
    b = rd(lo, ln)
    words = [int.from_bytes(b[i:i + 4], "little") for i in range(0, len(b) - 3, 4)]
    has_jr = any(w == 0x03E00008 for w in words)
    has_jal = any((w >> 26) == 3 for w in words)
    prologue = any(w & 0xFFFF0000 == 0x27BD0000 and (w & 0xFFFF) >= 0x8000
                   for w in words)
    ascii_frac = sum(1 for c in b if 32 <= c < 127 or c in (0, 10)) / max(1, len(b))
    zero_frac = b.count(0) / max(1, len(b))
    print("0x%08X len %-4d  jr_ra=%-5s jal=%-5s prologue=%-5s ascii=%.2f zero=%.2f"
          % (lo, ln, has_jr, has_jal, prologue, ascii_frac, zero_frac))
    print("   ", b[:32].hex())
