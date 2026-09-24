#!/usr/bin/env python3
"""Capture per-frame vertex streams while the view turns, for tools/sprite_track.py.

Usage: python tools/sprite_capture.py [--samples 150] [--dx 1] [--hold left] [--sleep 0.04]
       [--out logs/sprite_frames.json]
Each sample nudges the view, then stores one completed guest frame of the GPU
seam census: rows of (x, y, src, prim, addr) in draw order, three per triangle.
"""
import csv
import json
import os
import sys
import time

from ask import ask
from input_probe import BUTTONS

PORT = 4624
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def q(**k):
    return ask(PORT, json.dumps(k), timeout=20.0, tries=2)


def main():
    a = sys.argv[1:]
    samples = int(a[a.index("--samples") + 1]) if "--samples" in a else 150
    dx = int(a[a.index("--dx") + 1]) if "--dx" in a else 1
    hold = a[a.index("--hold") + 1] if "--hold" in a else ""
    out = a[a.index("--out") + 1] if "--out" in a else os.path.join(ROOT, "logs", "sprite_frames.json")
    pause = float(a[a.index("--sleep") + 1]) if "--sleep" in a else 0.04
    path = os.path.join(ROOT, "logs", "sprite_track.csv").replace(os.sep, "/")
    q(cmd="clear_input")
    q(cmd="seam_dump", path=path)
    time.sleep(0.5)
    if hold:
        mask = 0xFFFF
        for b in hold.split(","):
            mask &= ~BUTTONS[b]
        q(cmd="set_input", buttons=mask)
    frames, last = [], None
    for _ in range(samples):
        if dx:
            q(cmd="host_mouse", dx=dx)
        time.sleep(pause)
        r = q(cmd="seam_dump", path=path)
        if not r.get("ok") or not r.get("vertices"):
            continue
        rows, fr = [], None
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                fr = int(row["frame"])
                rows.append([int(row["x16"]) / 65536.0, int(row["y16"]) / 65536.0,
                             int(row["src"]), int(row["prim"]), int(row["addr"], 16)])
        if fr is None or fr == last:
            continue
        last = fr
        frames.append({"frame": fr, "rows": rows})
    q(cmd="clear_input")
    json.dump(frames, open(out, "w"))
    print("frames captured: %d -> %s" % (len(frames), out))


if __name__ == "__main__":
    main()
