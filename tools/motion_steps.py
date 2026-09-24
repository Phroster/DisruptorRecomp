#!/usr/bin/env python3
"""Per-frame camera motion: are the movement steps even at 60 fps?

Usage: python tools/motion_steps.py [--slot N] [--hold up,l2] [--seconds 3]
       (diagnostics build; works headless)

Write-traces the render camera position (0x800775C8 x, CC y, D0 z - the words
the sector loop hands to the terrain renderer) while holding pad buttons, then
prints the per-write step sizes. A steady walk should give equal steps; a
pattern like 12, 0, 12, 0 or 5, 7, 5, 7 means the motion advances unevenly
although every frame is new.
"""
import collections
import json
import sys
import time

from ask import ask
from input_probe import BUTTONS

PORT = 4624
CAM = 0x775C8


def q(c, **k):
    d = {"cmd": c}
    d.update(k)
    return ask(PORT, json.dumps(d), timeout=20.0, tries=2)


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 3.0
    hold = a[a.index("--hold") + 1].split(",") if "--hold" in a else ["up"]
    if "--slot" in a:
        q("savestate", op="load", slot=int(a[a.index("--slot") + 1]))
        time.sleep(4)
    mask = 0xFFFF
    for b in hold:
        mask &= ~BUTTONS[b]
    q("set_input", buttons=mask)
    time.sleep(1.0)                      # reach steady speed
    q("wtrace_del")
    print("arm:", q("wtrace_range", lo="0x%X" % CAM, hi="0x%X" % (CAM + 12)))
    t0 = q("wtrace_dump", count=1, newest=1).get("total", 0)
    time.sleep(secs)
    t1 = q("wtrace_dump", count=1, newest=1).get("total", 0)
    n = max(1, min(2048, int(t1) - int(t0)))
    print("trace entries written in the window: %d (using the newest %d)" % (int(t1) - int(t0), n))
    d = q("wtrace_dump", count=n, newest=1, addr_lo="0x%X" % CAM, addr_hi="0x%X" % (CAM + 11))
    q("wtrace_del")
    q("clear_input")
    ents = sorted(d.get("entries", []), key=lambda e: e.get("seq", 0))
    print("writes captured: %d (total %s) | sample: %s" % (len(ents), d.get("total"), json.dumps(ents[:1])[:260]))
    by = collections.defaultdict(list)
    for e in ents:
        addr = int(str(e.get("addr", "0")), 16) if isinstance(e.get("addr"), str) else e.get("addr", 0)
        val = e.get("new", e.get("val", e.get("value")))
        val = int(val, 16) if isinstance(val, str) else val
        if val is None:
            continue
        if val & 0x80000000:
            val -= 1 << 32
        by[addr & 0xFFFFFF].append((e.get("frame"), val))
    import math
    per_frame = {}
    for i, addr in enumerate(sorted(by)[:3]):
        for fr, val in by[addr]:
            per_frame.setdefault(fr, [None, None, None])[i] = val      # last write of the frame wins
    frames = sorted(f for f, v in per_frame.items() if None not in v)
    print("frames with a complete camera position:", len(frames))
    dist, gaps = [], collections.Counter()
    for f0, f1 in zip(frames, frames[1:]):
        gaps[f1 - f0] += 1
        if f1 - f0 != 1:
            continue
        a_, b = per_frame[f0], per_frame[f1]
        dist.append(math.hypot(b[0] - a_[0], b[1] - a_[1]))
    print("frame-number gaps:", sorted(gaps.items())[:6])
    print("horizontal distance moved per frame (first 60):", [round(x, 1) for x in dist[:60]])
    if len(dist) > 20:
        mid = sorted(dist)[len(dist) // 2]
        dev = [abs(x - mid) / mid for x in dist if mid > 0]
        print("median step %.2f | frames deviating >25%% from the median: %d of %d (%.0f%%) | zero-motion frames: %d"
              % (mid, sum(1 for x in dev if x > 0.25), len(dist), 100.0 * sum(1 for x in dev if x > 0.25) / len(dist),
                 sum(1 for x in dist if x == 0)))
        alt = sum(1 for a_, b, c in zip(dist, dist[1:], dist[2:]) if (b - a_) * (c - b) < 0 and abs(b - a_) > 0.2 * mid)
        print("alternating (saw-tooth) triples: %d of %d" % (alt, max(1, len(dist) - 2)))


if __name__ == "__main__":
    main()
