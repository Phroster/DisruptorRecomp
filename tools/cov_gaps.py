#!/usr/bin/env python3
"""List the uncovered gaps in the static EXE text from the ranges manifest.

Usage: python tools/cov_gaps.py [ranges-file]
"""
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "generated/SLUS_002.24_full.ranges"
LO, HI = 0x80010000, 0x80071800

ivals = []
for line in open(path, encoding="utf-8", errors="replace"):
    m = re.match(r"^R\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]+)\s*$", line.strip())
    if m:
        lo = int(m.group(1), 16)
        ln = int(m.group(2), 16)
        if ln:
            ivals.append((lo, lo + ln))

if not ivals:
    print("no R entries in", path)
    sys.exit(0)

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
    lo = max(lo, LO)
    hi = min(hi, HI)
    if hi <= lo:
        continue
    if lo > cur:
        gaps.append((cur, lo - cur))
    cur = max(cur, hi)
if cur < HI:
    gaps.append((cur, HI - cur))

total = HI - LO
covered = total - sum(g[1] for g in gaps)
print("text 0x%X..0x%X  ranges=%d  covered=%.2f%%  gaps=%d"
      % (LO, HI, len(merged), 100.0 * covered / total, len(gaps)))
for lo, ln in gaps:
    print("  gap 0x%08X  len 0x%X (%d bytes)" % (lo, ln, ln))
