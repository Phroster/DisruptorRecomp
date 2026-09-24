#!/usr/bin/env python3
"""Boot-to-intro A/B sample: MDEC, CD and audio counters after a fixed number
of guest VBlanks with no input (the intro videos play by themselves).

Usage: python tools/fmv_ab.py [--vblanks 2400]
Compare the printed line between two builds: a video path that starves or
races shows up as a different decoded-frame / sector / underrun count.
"""
import json
import sys
import time

from ask import ask

PORT = 4624


def q(c, **k):
    d = {"cmd": c}
    d.update(k)
    return ask(PORT, json.dumps(d), timeout=20.0, tries=3)


def pick(d, *names):
    return {n: d[n] for n in names if n in d}


def main():
    a = sys.argv[1:]
    target = int(a[a.index("--vblanks") + 1]) if "--vblanks" in a else 2400
    while q("vblank_rate")["delivered"] < target:
        time.sleep(0.25)
    v = q("vblank_rate")["delivered"]
    print("vblanks", v)
    for cmd in ("mdec_state", "cdrom_state", "audio_stats"):
        d = q(cmd)
        flat = {k: x for k, x in d.items() if isinstance(x, (int, float, str)) and k not in ("id",)}
        print(cmd, json.dumps(flat)[:700])


if __name__ == "__main__":
    main()
