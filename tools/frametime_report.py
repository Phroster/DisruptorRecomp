#!/usr/bin/env python3
"""Analyse a tools/frametime_record.py capture: how even is the cadence, and
what do the bad frames have in common?

Usage: python tools/frametime_report.py [logs/frametimes.json]
"""
import collections
import json
import statistics
import sys

PERIOD = 16683.4   # us, 59.94 Hz


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p))]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "logs/frametimes.json"
    d = json.load(open(path))
    rows = [r for r in d["frames"] if "d_present" in r]
    n = len(rows)
    if n < 100:
        print("too few frames (or a capture from the old recorder):", n)
        return
    deferred = sum(r["deferred"] for r in rows) > n / 2
    dp = [r["d_present"] for r in rows]
    print("frames analysed: %d | pacing: %s" % (
        n, "deferred (wait is the last thing before Present)" if deferred else "before compose"))
    print("present-to-present us: p50 %.0f  p05 %.0f  p95 %.0f  p99 %.0f  max %.0f  stdev %.0f"
          % (pct(dp, .5), pct(dp, .05), pct(dp, .95), pct(dp, .99), max(dp), statistics.pstdev(dp)))
    for tol in (250, 500, 1000, 2000):
        ok = sum(1 for x in dp if abs(x - PERIOD) <= tol)
        print("   within +-%4d us of 16683: %5.1f%%" % (tol, 100.0 * ok / n))
    prep = [r["prep"] for r in rows]
    print("%s us: p50 %.0f p95 %.0f p99 %.0f max %.0f" % (
        "compose+blit+copy+wait" if deferred else "compose+blit+copy+Present",
        pct(prep, .5), pct(prep, .95), pct(prep, .99), max(prep)))
    if deferred:
        fc = [r["flip_call"] for r in rows]
        print("Present() call us: p50 %.0f p95 %.0f p99 %.0f max %.0f"
              % (pct(fc, .5), pct(fc, .95), pct(fc, .99), max(fc)))

    bad = [r for r in rows if abs(r["d_present"] - PERIOD) > 1000]
    print("\nframes off by more than 1 ms: %d (%.1f%%)" % (len(bad), 100.0 * len(bad) / n))
    cause = collections.Counter()
    for r in bad:
        rel = r["d_paced"] - PERIOD
        late = r["d_present"] > PERIOD
        if late and rel > 800:
            cause["late: frame not ready by its deadline (game thread / GPU sync overran)"
                  if deferred else "late: pacer released late (work overran)"] += 1
        elif late:
            cause["late: the Present() call itself blocked"
                  if deferred else "late: present work after the pacer took long"] += 1
        elif rel < -800:
            cause["early: catch-up after a late frame (deadline pacer)"] += 1
        else:
            cause["early: the previous present was the slow one"] += 1
    for k, v in cause.most_common():
        print("   %4d  %s" % (v, k))
    big = [r for r in rows if r["d_present"] - PERIOD > 4000]
    print("\nhitches (> +4 ms): %d" % len(big))
    for r in big[:25]:
        print("   f=%d present %+6.1f ms | pacer %+6.1f ms | prep %.1f ms | Present() %.2f ms"
              % (r["f"], (r["d_present"] - PERIOD) / 1000, (r["d_paced"] - PERIOD) / 1000,
                 r["prep"] / 1000, r["flip_call"] / 1000))

    print("\nper-5s context:")
    prev = None
    for s in d["samples"]:
        fp = (s.get("frame_perf") or {})
        w = fp.get("wide_16_9", {}) if fp.get("wide_frames") else fp.get("all", {})
        dirty = (s.get("dirty") or {})
        ov = (s.get("overlay") or {})
        di = dirty.get("insns_run", 0) - (prev or {}).get("insns", dirty.get("insns_run", 0))
        ld = ov.get("loads", 0) - (prev or {}).get("loads", ov.get("loads", 0))
        print("   t=%5.1f wide=%s scene_gpu avg %.1f max %.1f ms | mirror avg %.1f (%s passes) | "
              "present_gpu %.1f | interp +%d | shard loads +%d"
              % (s["t"], fp.get("wide_frames"), w.get("scene_gpu_ms_avg", 0), w.get("scene_gpu_ms_max", 0),
                 w.get("mirror_gpu_ms_avg", 0), w.get("mirror_passes_avg", "-"),
                 fp.get("all", {}).get("present_gpu_ms_avg", 0), di, ld))
        prev = {"insns": dirty.get("insns_run", 0), "loads": ov.get("loads", 0)}


if __name__ == "__main__":
    main()
