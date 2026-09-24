#!/usr/bin/env python3
"""Present/interp/coherency diagnostics from the live visual instance."""
import collections
import json
import time

from input_probe import send

print("gl_interp:", json.dumps(send(4624, '{"cmd":"gl_interp"}'), indent=1))

time.sleep(2.0)

pr = send(4624, '{"cmd":"present_ring","n":1200}')
ev = pr.get("events", [])
print("present_ring total=%s events=%d" % (pr.get("total"), len(ev)))
if ev:
    print("entry[0..1]:", ev[0], ev[1])
    frames = [e[1] for e in ev]
    uniq = sorted(set(frames))
    span_frames = uniq[-1] - uniq[0]
    print("frames covered: %d distinct over %d guest frames" % (len(uniq), span_frames))
    per = collections.Counter(frames)
    print("presents per guest frame: min=%d max=%d avg=%.2f" %
          (min(per.values()), max(per.values()), len(ev) / span_frames))
    paths = collections.Counter(e[2] for e in ev)
    print("paths:", dict(paths))
    # frame gaps: how many guest frames get no present?
    missing = [f for f in range(uniq[0], uniq[-1] + 1) if f not in per]
    print("guest frames with no present: %d/%d" % (len(missing), span_frames))
    print("tag_delta sample:", [e[9] for e in ev[-12:]])

coh = send(4624, '{"cmd":"gl_coh_ring","n":2000}')
ce = coh.get("events", [])
print("coh events=%d" % len(ce))
if ce:
    print("coh entry[-1]:", ce[-1])
    kinds = collections.Counter(isinstance(x, dict) and x.get("kind") or a for x, a in [(e, None) for e in ce])
    print("kinds:", {k: v for k, v in list(kinds.items())[:8]})
