#!/usr/bin/env python3
"""Look for writes to candidate flag addresses in the saved frame logs."""
import json

CANDS = [0x71934, 0x71698, 0x5B920, 0x5A860, 0x5A85C, 0x5A866]

for name in ("d1", "e", "d2"):
    entries = json.load(open("logs/frame_%s.json" % name))["entries"]
    print("== frame_%s (%d entries)" % (name, len(entries)))
    for e in entries:
        a = int(e["addr"], 16)
        if a in CANDS:
            print("   %s %s = %s pc=%s" % (e["kind"], e["addr"], e["val"], e["pc"]))
