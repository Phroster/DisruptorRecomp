#!/usr/bin/env python3
"""Analyze captured CD/DMA histories: find overlay loads (low-RAM DMA dests).

Usage: python tools/cd_analyze.py [dma-json]
"""
import collections
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "logs/dma_cdrom.json"
d = json.load(open(path, encoding="utf-8", errors="replace"))
entries = d.get("entries", [])
print("entries:", len(entries), "total:", d.get("total"))

hist = collections.Counter()
pcs = collections.Counter()
for e in entries:
    a = e.get("start_addr", 0)
    if isinstance(a, str):
        a = int(a, 16)
    hist[(a >> 16) & 0x3F] += 1
    pcs[e.get("pc")] += 1

print("DMA dest page histogram (top 12):")
for page, n in hist.most_common(12):
    print("  dest 0x%02X0000-0x%02XFFFF : %d" % (page, page, n))
print("trigger PCs (top 10):")
for pc, n in pcs.most_common(10):
    print("  %s : %d" % (pc, n))

print()
print("last 32 transfers (lba, dest, words, pc):")
for e in entries[-32:]:
    print("  lba %-7s -> %s  words %-6s size %-5s pc %s"
          % (e.get("lba"), e.get("start_addr"), e.get("requested_words"),
             e.get("sector_size"), e.get("pc")))
