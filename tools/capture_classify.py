#!/usr/bin/env python3
"""Classify captured overlay regions: EXE-resident vs BIOS kernel vs true overlay.

Usage: python tools/capture_classify.py
"""
import base64
import collections
import glob
import hashlib
import json

EXE = open("input/SLUS_002.24", "rb").read()
EXE_LO = 0x80010000
EXE_SIZE = 0x800 + 0x61800

recs = []
for path in ["build/overlay_captures.json"] + sorted(
        glob.glob("build/overlay_captures.json.d/*.json")):
    try:
        data = json.load(open(path, encoding="utf-8", errors="replace"))
    except Exception as e:
        print("skip", path, e)
        continue
    for r in data:
        if isinstance(r, dict) and "bytes_b64" in r:
            recs.append(r)

print("records:", len(recs))

uniq = {}
for r in recs:
    b = base64.b64decode(r["bytes_b64"])
    key = (r["load_addr"], r.get("size"), hashlib.sha1(b).hexdigest())
    uniq[key] = (r, b)

print("unique region snapshots:", len(uniq))

kinds = collections.Counter()
regions = {}
for (la, size, _h), (r, b) in uniq.items():
    va = int(la, 16)
    phys = va & 0x1FFFFFFF
    if phys < 0x10000:
        kind = "bios-kernel-window"
    else:
        off = (va - EXE_LO) & 0xFFFFFFFF
        # compare the overlapping part against the EXE image
        if off < EXE_SIZE:
            exe_part = EXE[0x800 + off:0x800 + off + len(b)]
            cmp = min(len(exe_part), len(b))
            if cmp > 0:
                eq = sum(1 for i in range(cmp) if exe_part[i] == b[i])
                frac = eq / cmp
            else:
                frac = 0.0
            kind = ("exe-image-identical" if frac > 0.999 else
                    ("exe-image-partial" if frac > 0.5 else "overlay-or-other"))
            kinds[kind + " (%.2f)" % frac] += 1
            region = (phys >> 12)
            regions.setdefault(region, [kind, frac, 0])
            regions[region][2] += 1
            continue
        kind = "outside-exe"
    kinds[kind] += 1

print()
for k, n in kinds.most_common(20):
    print("  %-34s %d" % (k, n))

print()
print("non-EXE-identical regions by page:")
for page, (kind, frac, n) in sorted(regions.items()):
    if kind != "exe-image-identical":
        print("  page 0x%02X000  %-20s frac=%.2f  records=%d"
              % (page, kind, frac, n))
