#!/usr/bin/env python3
"""Cross-reference captured executed PCs against seeds and the dispatch table.

Usage: python tools/seed_gap.py
"""
import glob
import json
import re

seeds = set()
for line in open("input/functions.txt", encoding="utf-8", errors="replace"):
    line = line.strip()
    if line.startswith("0x") or line.startswith("0X"):
        seeds.add(int(line, 16) & 0x1FFFFFFF)

disp = set()
for line in open("generated/SLUS_002.24_dispatch.c", encoding="utf-8",
                 errors="replace"):
    for m in re.finditer(r"0x80([0-9A-Fa-f]{6})u", line):
        disp.add(int("80" + m.group(1), 16) & 0x1FFFFFFF)

covered = set()
for line in open("generated/SLUS_002.24_full.ranges", encoding="utf-8",
                 errors="replace"):
    m = re.match(r"^R\s+80([0-9A-Fa-f]{6})\s+([0-9A-Fa-f]+)", line.strip())
    if m:
        lo = int("80" + m.group(1), 16) & 0x1FFFFFFF
        ln = int(m.group(2), 16)
        for a in range(lo, lo + ln, 4):
            covered.add(a)

pcs = set()
for path in ["build/overlay_captures.json"] + sorted(
        glob.glob("build/overlay_captures.json.d/*.json")):
    try:
        data = json.load(open(path, encoding="utf-8", errors="replace"))
    except Exception:
        continue
    for r in data:
        if isinstance(r, dict):
            for p in r.get("executed_pcs", []):
                if isinstance(p, str) and p.lower().startswith("0x"):
                    pcs.add(int(p, 16) & 0x1FFFFFFF)

TEXT = set(range(0x10000, 0x71800, 4))
texec = sorted(p for p in pcs if p in TEXT and 0x80000 <= p or True)
texec = sorted(p for p in pcs if 0x10000 <= p < 0x71800)

in_seed = [p for p in texec if p in seeds]
in_disp = [p for p in texec if p in disp]
covered_not_entry = [p for p in texec if p in covered and p not in disp]
gap = [p for p in texec if p not in covered]

print("captured executed PCs (EXE text):", len(texec))
print("  already in seed file:", len(in_seed))
print("  in dispatch table:", len(in_disp))
print("  covered by a range but not a dispatch entry:", len(covered_not_entry))
print("  inside uncovered gaps:", len(gap))
print()
print("gap PCs (candidates to add as seeds):")
print(" ", [hex(p) for p in sorted(set(gap))[:40]])
print()
print("covered-not-entry PCs (interior jumps; candidates for entry scan):")
print(" ", [hex(p) for p in sorted(set(covered_not_entry))[:40]])
