#!/usr/bin/env python3
"""Attribute hitches: sample the runtime's rings repeatedly and save them.

Usage: python tools/attribute.py [--seconds 75] [--interval 5]
"""
import json
import os
import sys
import time

from ask import ask

PORT = 4624
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "attribute")


def grab(cmd, extra=None):
    payload = {"cmd": cmd}
    if extra:
        payload.update(extra)
    return ask(PORT, json.dumps(payload), timeout=4.0, tries=3)


def main():
    seconds = 75
    interval = 5
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])
    if "--interval" in sys.argv:
        interval = float(sys.argv[sys.argv.index("--interval") + 1])
    os.makedirs(OUT, exist_ok=True)
    end = time.time() + seconds
    n = 0
    while time.time() < end:
        for cmd, extra in (
            ("latency", None),
            ("frame_perf", None),
            ("phase_hot", {"top": 16}),
            ("starv_ring", {"count": 64}),
            ("gl_coh_ring", {"n": 256}),
        ):
            try:
                r = grab(cmd, extra)
            except Exception as exc:
                r = {"error": str(exc)}
            path = os.path.join(OUT, f"{cmd}_{n:03d}.json")
            with open(path, "w") as fh:
                json.dump(r, fh)
        lat = None
        try:
            with open(os.path.join(OUT, f"latency_{n:03d}.json")) as fh:
                s = json.load(fh).get("summary", {})
                fp = s.get("frame_period", {})
                lat = (fp.get("p50_us"), fp.get("p95_us"), fp.get("max_us"))
        except Exception:
            pass
        print(f"[{n}] {time.strftime('%H:%M:%S')} frame_us p50/p95/max="
              f"{lat}", flush=True)
        n += 1
        time.sleep(interval)
    print("done", n, flush=True)


if __name__ == "__main__":
    main()
