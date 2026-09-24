#!/usr/bin/env python3
"""GL swap ring (all swaps incl. interpolation) + rate over a short window."""
import collections
import sys
import time

from input_probe import send

port = int(sys.argv[1]) if len(sys.argv) > 1 else 4624


def snap():
    r = send(port, '{"cmd":"gl_present_ring","n":1200}')
    return r


a = snap()
time.sleep(3.0)
b = snap()

ev = b.get("events", [])
print("total a=%s b=%s (+%d in 3s)" % (a.get("total"), b.get("total"),
                                       (b.get("total", 0) - a.get("total", 0))))
print("events=%d" % len(ev))
paths = collections.Counter(e[2] for e in ev)
print("paths:", dict(paths))
frames = [e[1] for e in ev]
if frames:
    span = max(frames) - min(frames)
    print("guest frames spanned: %d -> %.2f swaps/guest-frame" %
          (span, len(ev) / span if span else 0))
print("first:", ev[0] if ev else None)
print("last:", ev[-1] if ev else None)
