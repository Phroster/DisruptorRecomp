#!/usr/bin/env python3
"""Watch the engine's real frame rate while the user plays.

Usage: python tools/fps_monitor.py [--seconds 180] [--out logs/fps_monitor.json]

The runtime only presents when the game flipped its display buffer, and its
present ring records the guest VBlank number of every present. A step of 2
between consecutive presents means the engine needed two VBlanks for that
frame (its update + render did not fit the guest CPU budget of one VBlank), so
one picture is missing: that is a real drop below 60 fps, independent of host
frame pacing. This polls the ring, merges by present sequence and reports, per
second, presents and skipped guest frames, plus the polygon load.
"""
import collections
import json
import sys
import time

from ask import ask

PORT = 4624


def q(cmd, **kw):
    d = {"cmd": cmd}
    d.update(kw)
    try:
        return ask(PORT, json.dumps(d), timeout=5.0, tries=2)
    except Exception:
        return None


def main():
    a = sys.argv[1:]
    secs = int(a[a.index("--seconds") + 1]) if "--seconds" in a else 180
    out = a[a.index("--out") + 1] if "--out" in a else "logs/fps_monitor.json"
    ev = {}
    perf = []
    start = time.time()
    nxt = 0.0
    while time.time() - start < secs:
        r = q("gl_present_ring", n=400)
        for e in (r or {}).get("events") or []:
            ev[e[0]] = (e[1], e[3], e[2])          # seq -> (guest frame, ms, mode)
        now = time.time() - start
        if now >= nxt:
            nxt = now + 5.0
            fp = q("frame_perf") or {}
            w = fp.get("wide_16_9") or {}
            perf.append({"t": round(now, 1), "prims": w.get("prims_avg"),
                         "scene_gpu": w.get("scene_gpu_ms_avg"), "wide": fp.get("wide_frames")})
        time.sleep(1.5)
    seqs = sorted(ev)
    rows = [(ev[s][0], ev[s][1], ev[s][2]) for s in seqs]
    per_sec = collections.OrderedDict()
    skipped_total = 0
    for (f0, t0, m0), (f1, t1, m1) in zip(rows, rows[1:]):
        sec = t1 // 1000
        d = per_sec.setdefault(sec, {"presents": 0, "skipped": 0, "wide": 0})
        d["presents"] += 1
        d["wide"] += 1 if m1 == "wide" else 0
        step = f1 - f0
        if 1 < step < 8:
            d["skipped"] += step - 1
            skipped_total += step - 1
    game = {s: d for s, d in per_sec.items() if d["wide"] >= d["presents"] * 0.8 and d["presents"] > 20}
    n = len(game)
    print("gameplay seconds observed: %d | presents: %d | guest frames skipped: %d (%.2f%%)"
          % (n, sum(d["presents"] for d in game.values()), sum(d["skipped"] for d in game.values()),
             100.0 * sum(d["skipped"] for d in game.values()) /
             max(1, sum(d["presents"] + d["skipped"] for d in game.values()))))
    hist = collections.Counter(d["presents"] for d in game.values())
    print("presents-per-second histogram:", sorted(hist.items()))
    bad = [(s, d) for s, d in game.items() if d["skipped"] > 0]
    print("seconds with skipped frames: %d" % len(bad))
    if game:
        base = min(game)
        for s, d in bad[:40]:
            print("   t=%4ds  presents %2d  skipped %2d" % (s - base, d["presents"], d["skipped"]))
    print("load samples (t, avg prims/frame, scene GPU ms):",
          [(p["t"], p["prims"], p["scene_gpu"]) for p in perf if p.get("wide")][:40])
    with open(out, "w") as fh:
        json.dump({"per_sec": {str(k): v for k, v in per_sec.items()}, "perf": perf}, fh)


if __name__ == "__main__":
    main()
