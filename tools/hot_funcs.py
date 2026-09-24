#!/usr/bin/env python3
"""Rank guest functions by host wall time over a window (diagnostics build).

Usage: python tools/hot_funcs.py [--seconds 8] [--slot N] [--top 16]
Diffs two phase_hot snapshots of the static-dispatch histogram.
"""
import json
import sys
import time

from ask import ask

PORT = 4624


def q(c, **k):
    d = {"cmd": c}
    d.update(k)
    return ask(PORT, json.dumps(d), timeout=20.0, tries=2)


def snap():
    r = q("phase_hot", set="static", top=64)
    return {e.get("addr", e.get("pc")): e.get("n", e.get("samples", e.get("count", 0))) for e in r.get("top", [])}, r


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 8.0
    top = int(a[a.index("--top") + 1]) if "--top" in a else 16
    if "--slot" in a:
        print(q("savestate", op="load", slot=int(a[a.index("--slot") + 1])))
        time.sleep(4)
    s0, raw = snap()
    if not s0:
        print("phase_hot returned:", json.dumps(raw)[:300])
    time.sleep(secs)
    s1, _ = snap()
    d = {k: s1[k] - s0.get(k, 0) for k in s1}
    tot = sum(d.values()) or 1
    pp = q("phase_profile", window=int(secs))
    print("phase shares:", {k: pp[k] for k in ("static_share", "gpu_share", "exc_share", "other_share", "interp_share")})
    for addr, n in sorted(d.items(), key=lambda kv: -kv[1])[:top]:
        print("   %s  %5.1f%%  (%d samples)" % (addr, 100.0 * n / tot, n))


if __name__ == "__main__":
    main()
