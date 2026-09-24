#!/usr/bin/env python3
"""Drawn-frame fraction over consecutive frames + sync-var write counts."""
import json
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
st = send(PORT, '{"cmd":"gpu_ring_stats"}')
newest = st["newest_frame"]
drawn = 0
n = 12
for f in range(newest - n + 1, newest + 1):
    r = send(PORT, '{"cmd":"gpu_frame_dump","frame":%d,"count":4}' % f)
    if r.get("count", 0) > 0:
        drawn += 1
print("drawn frames: %d/%d" % (drawn, n))

for name in ("d1", "e", "d2"):
    try:
        entries = json.load(open("logs/frame_%s.json" % name))["entries"]
    except Exception as exc:
        print(name, "ERR", exc)
        continue
    cnt = sum(1 for e in entries if int(e["addr"], 16) == 0x5A860)
    print("frame_%s: entries=%d 0x5A860 writes=%d" % (name, len(entries), cnt))
