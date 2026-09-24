#!/usr/bin/env python3
"""Print low-RAM CD DMA transfers (overlay/data loads) in order.

Usage: python tools/cd_low.py [dma-json]
"""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "logs/dma_boot.json"
d = json.load(open(path, encoding="utf-8", errors="replace"))
entries = d.get("entries", [])

for e in entries:
    a = e.get("start_addr", 0)
    if isinstance(a, str):
        a = int(a, 16)
    if a < 0x100000:
        print("lba %-7s -> 0x%06X words %-5s size %-5s pc %s"
              % (e.get("lba"), a, e.get("requested_words"),
                 e.get("sector_size"), e.get("pc")))
