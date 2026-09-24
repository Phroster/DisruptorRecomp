#!/usr/bin/env python3
"""Does the engine submit world polygons beyond the 4:3 screen edges?

Usage: python tools/ws_extent_check.py [--seconds 1.0]
Runs against the live game (any mode, headless works): records the GPU
primitive census for a moment, then reports, for the busiest recent frames,
how many polygons lie entirely in the 16:9 side bands (x < 0 or x >= 320), the
xmin/xmax histograms (a cliff at 0 / 320 = something still culls at the 4:3
edge), and the live portal windows.
"""
import collections
import csv
import json
import os
import struct
import sys
import time

from ask import ask

PORT = 4624


def q(c, **k):
    d = {"cmd": c}
    d.update(k)
    return ask(PORT, json.dumps(d), timeout=60.0, tries=2)


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 1.0
    out = os.path.abspath("logs/ws_extent_census.csv").replace(os.sep, "/")
    q("ws_census", action="on")
    time.sleep(secs)
    q("ws_census", action="off")
    q("ws_census", start=0, end=2000000000, out=out)
    rows = list(csv.DictReader(open(out)))
    per = collections.Counter(int(r["frame"]) for r in rows)
    newest = max(per)
    recent = [f for f in per if f > newest - 400]
    busy = sorted(recent, key=lambda f: -per[f])[:12]
    polys = [r for r in rows if int(r["frame"]) in set(busy) and 0x20 <= int(r["opcode"], 16) <= 0x3F]
    if not polys:
        print("no polygons in the recent frames (not in gameplay?)")
        return
    lo = [int(r["xmin"]) for r in polys]
    hi = [int(r["xmax"]) for r in polys]
    n = len(polys)
    print("frames %s | polygons %d | x range [%d, %d]" % (sorted(busy)[-3:], n, min(lo), max(hi)))
    print("entirely left of 0: %d | entirely right of 320: %d | past -53: %d | past 373: %d"
          % (sum(1 for x in hi if x < 0), sum(1 for x in lo if x >= 320),
             sum(1 for x in lo if x <= -53), sum(1 for x in hi if x >= 373)))
    hmin = collections.Counter(max(min(x // 32 * 32, 480), -160) for x in lo)
    hmax = collections.Counter(max(min(x // 32 * 32, 480), -160) for x in hi)
    print("xmin bins:", sorted(hmin.items()))
    print("xmax bins:", sorted(hmax.items()))
    r = q("read_ram", addr="0x80079D18", len=64)
    b = bytes.fromhex(r["hex"])
    print("portal windows (biased +64):",
          ["%d..%d" % (struct.unpack_from("<I", b, o)[0] >> 16, struct.unpack_from("<I", b, o)[0] & 0xFFFF)
           for o in range(0, 64, 8)])


if __name__ == "__main__":
    main()
