#!/usr/bin/env python3
"""Print present pacing of the running game (GL window required).

Usage: python tools/pace_report.py
"""
import collections
import json

from ask import ask

PORT = 4624


def main():
    r = ask(PORT, json.dumps({"cmd": "gl_present_ring", "n": 1200}), timeout=10.0, tries=2)
    ev = r.get("events") or []
    # steady state only: drop the boot/transition gaps
    ts = [e[3] for e in ev]
    fr = [e[1] for e in ev]
    dt = [b - a for a, b in zip(ts, ts[1:]) if b - a < 100]
    steps = collections.Counter(b - a for a, b in zip(fr, fr[1:]))
    n = len(dt)
    even = sum(1 for d in dt if 16 <= d <= 17)
    print("presents: %d | 16-17 ms: %.1f%% | <15 or >18 ms: %d" % (
        len(ev), 100.0 * even / max(1, n), sum(1 for d in dt if d < 15 or d > 18)))
    print("interval histogram (ms):", sorted(collections.Counter(dt).items()))
    print("guest frames skipped between presents:", sum(s - 1 for s in steps.elements() if 1 < s < 10))
    s = ask(PORT, json.dumps({"cmd": "latency", "window": 300}), timeout=10.0, tries=2).get("summary", {})
    print("present_mode (swap interval):", s.get("present_mode"))
    print("frame_period us:", s.get("frame_period"))
    print("swap_block us:", s.get("swap_block"))


if __name__ == "__main__":
    main()
