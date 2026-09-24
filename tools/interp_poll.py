#!/usr/bin/env python3
"""Poll interpolation state + present paths for a few seconds."""
import collections
import time

from input_probe import send

for i in range(25):
    gi = send(4624, '{"cmd":"gl_interp"}')
    pr = send(4624, '{"cmd":"present_ring","n":150}')
    ev = pr.get("events", [])
    paths = collections.Counter(e[2] for e in ev)
    frames = [e[1] for e in ev]
    span = (max(frames) - min(frames)) if frames else 0
    print("t=%4.1fs enabled=%d suspended=%d history=%d target=%.1f swaps=%d | %d presents over %d frames (%.2f/frame) %s" %
          (i * 0.2, gi["enabled"], gi["suspended"], gi["history"], gi["target_hz"],
           gi["swaps"], len(ev), span, (len(ev) / span) if span else 0, dict(paths)),
          flush=True)
    time.sleep(0.2)
