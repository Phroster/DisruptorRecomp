#!/usr/bin/env python3
"""At a screen edge: does the game still submit a sprite, and does the renderer
take it through the precise path?

Usage: python tools/sprite_edge_probe.py [--pre 110] [--n 40] [--dx 1]
Turns the view --pre steps, then for --n more steps prints the engine's sprite
list (0x80079E98: 20-byte entries, x/y/w/h as halves at +4/+6/+10/+12) next to
the sprite quads the GPU seam census saw (triangle path only).
"""
import csv
import json
import os
import struct
import sys
import time

from ask import ask

PORT = 4624
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = 0x80079E98


def q(**k):
    return ask(PORT, json.dumps(k), timeout=20.0, tries=2)


def main():
    a = sys.argv[1:]
    pre = int(a[a.index("--pre") + 1]) if "--pre" in a else 110
    n = int(a[a.index("--n") + 1]) if "--n" in a else 40
    dx = int(a[a.index("--dx") + 1]) if "--dx" in a else 1
    path = os.path.join(ROOT, "logs", "sprite_edge.csv").replace(os.sep, "/")
    q(cmd="seam_dump", path=path)
    for _ in range(pre):
        q(cmd="host_mouse", dx=dx)
        time.sleep(0.04)
    for i in range(n):
        q(cmd="host_mouse", dx=dx)
        time.sleep(0.06)
        q(cmd="seam_dump", path=path)
        r = q(cmd="read_ram", addr="0x%08X" % LIST, len=20 * 8)
        raw = bytes.fromhex(r.get("hex") or r.get("data") or "")
        ents = []
        for e in range(len(raw) // 20):
            x, y, zk, w, h = struct.unpack_from("<hhhhh", raw, e * 20 + 4)
            if w > 20 or w < -20:
                ents.append((x, y, w, h))
        quads = []
        rows = list(csv.DictReader(open(path, newline="")))
        k = 0
        while k + 5 < len(rows):
            p = int(rows[k]["prim"])
            if 0x2C <= p <= 0x2F:
                xs = [int(rows[j]["x16"]) / 65536.0 for j in range(k, k + 6)]
                if max(xs) - min(xs) > 20:
                    quads.append((round(min(xs), 1), round(max(xs), 1)))
                k += 6
            else:
                k += 1
        print("%3d list(x,y,w,h)=%s | precise quads x=%s" % (i, ents, quads))


if __name__ == "__main__":
    main()
