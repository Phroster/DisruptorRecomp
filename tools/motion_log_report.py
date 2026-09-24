#!/usr/bin/env python3
"""Analyse a DISRUPTOR_MOTION_LOG capture (one row per guest frame).

Usage: python tools/motion_log_report.py [logs/motion_log.csv]

Reports, for the frames in which the player was actually moving or turning:
 - host time between guest frames (is the simulation itself delivered evenly?)
 - how even the per-frame movement distance and turn are. Steps like
   5,5,5,5 are smooth; 0,10,0,10 or 3,7,3,7 look like half the frame rate even
   though every frame is new and on time.
"""
import csv
import math
import statistics
import sys


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p))]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "logs/motion_log.csv"
    rows = [dict((k, float(v)) for k, v in r.items()) for r in csv.DictReader(open(path))]
    n = len(rows)
    print("guest frames logged: %d (%.0f s)" % (n, (rows[-1]["host_us"] - rows[0]["host_us"]) / 1e6))
    dt = [b["host_us"] - a["host_us"] for a, b in zip(rows, rows[1:])]
    print("host time per guest frame us: p50 %.0f p05 %.0f p95 %.0f p99 %.0f max %.0f"
          % (pct(dt, .5), pct(dt, .05), pct(dt, .95), pct(dt, .99), max(dt)))
    print("   frames later than 20 ms: %d | later than 25 ms: %d | later than 33 ms: %d"
          % (sum(1 for x in dt if x > 20000), sum(1 for x in dt if x > 25000), sum(1 for x in dt if x > 33000)))
    step = [math.hypot(b["x"] - a["x"], b["y"] - a["y"]) for a, b in zip(rows, rows[1:])]
    turn = []
    for a, b in zip(rows, rows[1:]):
        d = (b["yaw"] + b["yaw_frac"]) - (a["yaw"] + a["yaw_frac"])
        d = (d + 128) % 256 - 128
        turn.append(d)
    # moving stretches: runs of >= 30 frames where the median step is clearly non-zero
    runs, cur = [], []
    for i, sdist in enumerate(step):
        if sdist > 0 or (cur and sum(1 for k in cur[-6:] if step[k] > 0) >= 2):
            cur.append(i)
        else:
            if len(cur) >= 30:
                runs.append(cur)
            cur = []
    if len(cur) >= 30:
        runs.append(cur)
    mv = [i for r in runs for i in r]
    print("frames inside sustained movement: %d in %d stretches" % (len(mv), len(runs)))
    if mv:
        zero = sum(1 for i in mv if step[i] == 0)
        print("   zero-distance frames while moving: %d (%.1f%%)" % (zero, 100.0 * zero / len(mv)))
        ratios, saw = [], 0
        for r in runs:
            for i0, i1, i2 in zip(r, r[1:], r[2:]):
                a, b, c = step[i0], step[i1], step[i2]
                m = (a + b + c) / 3.0
                if m <= 0:
                    continue
                ratios.append(abs(b - m) / m)
                if (b - a) * (c - b) < 0 and abs(b - a) > 0.3 * m and abs(c - b) > 0.3 * m:
                    saw += 1
        print("   step unevenness (|step - local mean| / mean): p50 %.2f p90 %.2f" % (pct(ratios, .5), pct(ratios, .9)))
        print("   saw-tooth triples (up-down-up by >30%%): %d of %d (%.1f%%)" % (saw, len(ratios), 100.0 * saw / max(1, len(ratios))))
        worst = max(runs, key=len)
        print("   longest stretch, first 48 steps:", [round(step[i], 1) for i in worst[:48]])
    tr = [t for t in turn if abs(t) > 0.01]
    if tr:
        print("turning frames: %d | per-frame turn (yaw units) first 40: %s" % (len(tr), [round(t, 2) for t in tr[:40]]))
    # slow host frames vs movement: where do the late frames fall?
    late = [i for i, x in enumerate(dt) if x > 20000]
    if late:
        print("late host frames (>20 ms) at guest frame:", late[:40])


if __name__ == "__main__":
    main()
