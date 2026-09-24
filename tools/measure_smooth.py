#!/usr/bin/env python3
"""Smoothness measurement on a live instance: present cadence, interpolation
state, latency summary, per-present frame tags."""
import collections
import json
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4624

print("== latency ==")
try:
    print(json.dumps(send(PORT, '{"cmd":"latency","window":600}'), indent=1)[:1800])
except Exception as exc:
    print("ERR", exc)

print("== gl_interp ==")
print(send(PORT, '{"cmd":"gl_interp"}'))

print("== gl_present_ring ==")
r = send(PORT, '{"cmd":"gl_present_ring","n":1200}')
ev = r.get("events", [])
print("total=%s events=%d" % (r.get("total"), len(ev)))
if ev:
    ts = [e[3] for e in ev]
    frames = [e[1] for e in ev]
    paths = collections.Counter(e[2] for e in ev)
    print("paths:", dict(paths))
    uniq = sorted(set(frames))
    span = uniq[-1] - uniq[0] if uniq else 0
    print("guest frames spanned: %d  presents: %d  presents/frame: %.2f"
          % (span, len(ev), (len(ev) / span) if span else 0))
    d = [b - a for a, b in zip(ts, ts[1:]) if 0 < b - a < 200]
    d.sort()
    if d:
        p = lambda q: d[min(len(d) - 1, int(len(d) * q))]
        print("present interval ms: p50=%d p90=%d p99=%d max=%d"
              % (p(.5), p(.9), p(.99), d[-1]))
