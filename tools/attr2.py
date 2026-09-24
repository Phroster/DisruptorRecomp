#!/usr/bin/env python3
"""High-rate attribution: latency + phase_profile + gl_present_ring every 2 s."""
import json
import os
import sys
import time

from ask import ask

PORT = 4624
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "attr2")


def main():
    seconds = int(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 80
    os.makedirs(OUT, exist_ok=True)
    end = time.time() + seconds
    n = 0
    while time.time() < end:
        lat = ask(PORT, json.dumps({"cmd": "latency"}), timeout=4.0, tries=3)
        prof = ask(PORT, json.dumps({"cmd": "phase_profile"}), timeout=4.0, tries=3)
        ring = ask(PORT, json.dumps({"cmd": "gl_present_ring", "n": 300}), timeout=4.0, tries=3)
        with open(os.path.join(OUT, f"lat_{n:03d}.json"), "w") as fh:
            json.dump(lat, fh)
        with open(os.path.join(OUT, f"prof_{n:03d}.json"), "w") as fh:
            json.dump(prof, fh)
        with open(os.path.join(OUT, f"ring_{n:03d}.json"), "w") as fh:
            json.dump(ring, fh)
        s = lat.get("summary", {})
        fp = s.get("frame_period", {})
        print(f"[{n}] {time.strftime('%H:%M:%S')} p50={fp.get('p50_us')} "
              f"p95={fp.get('p95_us')} max={fp.get('max_us')}", flush=True)
        n += 1
        time.sleep(2)
    print("done", n, flush=True)


if __name__ == "__main__":
    main()
