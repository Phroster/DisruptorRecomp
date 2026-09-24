#!/usr/bin/env python3
"""Are all 60 presented frames per second actually NEW pictures?

Usage: python tools/dup_frame_monitor.py [--seconds 120] [--chunk 8]
       (diagnostics build: run.ps1 -Diag; keep MOVING and TURNING while it runs)

The present counters only prove that the game flipped its buffer every VBlank.
If the engine's logic did not advance between two passes (elapsed-tick count 0,
then 2 on the next one - which happens when one pass takes about one VBlank of
guest CPU), the flipped picture is a duplicate and the next one jumps twice as
far: 60 presents per second that look like 30-40. This records the GPU
primitive census in chunks, fingerprints the polygon list of every guest frame
and reports duplicate frames, frames without any world geometry, and the
polygon load where they occur.
"""
import collections
import csv
import json
import os
import sys
import time
import zlib

from ask import ask

PORT = 4624


def q(c, **k):
    d = {"cmd": c}
    d.update(k)
    return ask(PORT, json.dumps(d), timeout=90.0, tries=2)


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 120.0
    chunk = float(a[a.index("--chunk") + 1]) if "--chunk" in a else 8.0
    out = os.path.abspath("logs/dup_census.csv").replace(os.sep, "/")
    # Discard whatever the census ring already holds: only frames recorded from
    # now on belong to this measurement.
    q("ws_census", action="on")
    time.sleep(0.3)
    q("ws_census", action="off")
    q("ws_census", start=0, end=2000000000, out=out)
    last_frame = -1
    with open(out, newline="") as fh:
        for r in csv.DictReader(fh):
            last_frame = max(last_frame, int(r["frame"]))
    end = time.time() + secs
    series = []            # (frame, fingerprint, polys)
    while time.time() < end:
        q("ws_census", action="on")
        time.sleep(chunk)
        q("ws_census", action="off")
        q("ws_census", start=last_frame + 1, end=2000000000, out=out)
        per = collections.OrderedDict()
        with open(out, newline="") as fh:
            for r in csv.DictReader(fh):
                op = int(r["opcode"], 16)
                if not (0x20 <= op <= 0x3F):
                    continue
                f = int(r["frame"])
                per.setdefault(f, []).append((op, r["x"], r["y"], r["xmin"], r["xmax"]))
        for f in sorted(per):
            if f <= last_frame:
                continue
            prims = per[f]
            fp = zlib.crc32(repr(sorted(prims)).encode())
            series.append((f, fp, len(prims)))
        if per:
            last_frame = max(per)
        print("  ... %d frames so far" % len(series), flush=True)

    game = [s for s in series if s[2] >= 200]        # frames with a 3D scene
    if len(game) < 120:
        print("not enough gameplay frames (%d)" % len(game))
        return
    dup = gap = 0
    game = game[30:]          # skip the first half second (input ramp-up)
    dup_at = []
    for (f0, p0, n0), (f1, p1, n1) in zip(game, game[1:]):
        if f1 - f0 > 1:
            gap += f1 - f0 - 1
        elif p0 == p1:
            dup += 1
            dup_at.append((f1, n1))
    n = len(game)
    print("gameplay frames: %d | duplicate pictures: %d (%.1f%%) | gaps between chunks (ignore): %d"
          % (n, dup, 100.0 * dup / n, gap))
    print("=> effective picture rate while recording: %.1f fps" % (59.94 * (n - dup) / n))
    polys = sorted(s[2] for s in game)
    print("polygons per frame: p50 %d  p95 %d  max %d" % (polys[n // 2], polys[int(n * .95)], polys[-1]))
    if dup_at:
        d = sorted(x[1] for x in dup_at)
        print("polygons per frame at the duplicates: p50 %d  min %d  max %d" % (d[len(d) // 2], d[0], d[-1]))
    # per-second view
    sec = collections.OrderedDict()
    base = game[0][0]
    dupset = set(x[0] for x in dup_at)
    for f, fp, npoly in game:
        s = (f - base) // 60
        e = sec.setdefault(s, [0, 0, 0])
        e[0] += 1
        e[1] += 1 if f in dupset else 0
        e[2] = max(e[2], npoly)
    bad = [(s, e) for s, e in sec.items() if e[1] >= 6]
    print("seconds with 6+ duplicate pictures: %d of %d" % (len(bad), len(sec)))
    for s, e in bad[:30]:
        print("   t=%4ds  new pictures %2d  duplicates %2d  max polys %d" % (s, e[0] - e[1], e[1], e[2]))


if __name__ == "__main__":
    main()
