#!/usr/bin/env python3
"""Measure the game-loop iteration rate: fntrace func_8001FBB8 call frames."""
import collections
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
TARGET = sys.argv[2] if len(sys.argv) > 2 else "0x8001FBB8"

print(send(PORT, '{"cmd":"fntrace_arm","target":"%s"}' % TARGET))
time.sleep(1.0)
d = send(PORT, '{"cmd":"fntrace_dump","target_lo":"%s","target_hi":"0x%08X","count":256}'
         % (TARGET, int(TARGET, 16) + 1))
ev = d.get("entries", [])
print("entries for target:", len(ev))
frames = [e["frame"] for e in ev]
uniq = sorted(set(frames))
print("distinct frames: %d  first: %s" % (len(uniq), uniq[:20]))
if len(uniq) > 1:
    gaps = [b - a for a, b in zip(uniq, uniq[1:])]
    print("frame gaps:", collections.Counter(gaps).most_common(8))
    total_span = uniq[-1] - uniq[0]
    calls_per_frame = len(ev) / total_span if total_span else 0
    print("calls/frame: %.2f" % calls_per_frame)
send(PORT, '{"cmd":"fntrace_arm_clear"}')
