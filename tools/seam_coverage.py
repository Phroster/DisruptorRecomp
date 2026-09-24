#!/usr/bin/env python3
"""Exact crack area of recorded frames, for a given crack-fill rule.

Usage: python tools/seam_coverage.py capture [--frames 8] [--hold left] [--out logs/seam_frames.json]
       python tools/seam_coverage.py eval logs/seam_frames.json

capture  records N guest frames of triangle vertices from the running GL build
         (debug verb seam_dump, runtime patch 014).
eval     rasterises every frame's triangles at 16x into a coverage mask, once
         per fill rule, and measures the THIN uncovered area inside the covered
         region (morphological closing minus the mask): the pixels a crack lets
         the background through. Texture content cannot confuse it. Area is
         reported in native pixels^2 per frame.

Fill rules mirror runtime patch 015: every triangle grown outward by d native
pixels (edge normals, miter capped at 4d); "adaptive" grows triangles that own
a whole-pixel vertex (the game's screen-space clipper output) by more.
"""
import csv
import json
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from ask import ask
from input_probe import BUTTONS

PORT = 4624
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 16          # raster scale
F = 65536.0


def q(**k):
    return ask(PORT, json.dumps(k), timeout=20.0, tries=2)


def capture(a):
    frames = int(a[a.index("--frames") + 1]) if "--frames" in a else 8
    out = a[a.index("--out") + 1] if "--out" in a else "logs/seam_frames.json"
    gap = float(a[a.index("--gap") + 1]) if "--gap" in a else 0.2
    mask = 0xFFFF
    for b in (a[a.index("--hold") + 1] if "--hold" in a else "left").split(","):
        mask &= ~BUTTONS[b]
    path = os.path.join(ROOT, "logs", "seam_frame.csv").replace(os.sep, "/")
    q(cmd="seam_dump", path=path)
    q(cmd="set_input", buttons=mask)
    time.sleep(0.5)
    got = {}
    end = time.time() + 40
    while len(got) < frames and time.time() < end:
        r = q(cmd="seam_dump", path=path)
        if not r.get("vertices"):
            continue
        rows = list(csv.DictReader(open(path, newline="")))
        f = int(rows[0]["frame"])
        if f not in got:
            got[f] = [(int(r["x16"]), int(r["y16"]), int(r["src"]), int(r["prim"])) for r in rows]
            time.sleep(gap)       # let the view move on
    q(cmd="clear_input")
    json.dump(got, open(out, "w"))
    print("captured %d frames -> %s" % (len(got), out))


def grow(tri, d):
    (x0, y0), (x1, y1), (x2, y2) = tri
    area2 = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(area2) < 1e-3 or d <= 0:
        return tri
    sgn = 1.0 if area2 > 0 else -1.0
    P = [(x0, y0), (x1, y1), (x2, y2)]
    n = []
    for i in range(3):
        ax, ay = P[i]
        bx, by = P[(i + 1) % 3]
        ex, ey = bx - ax, by - ay
        L = (ex * ex + ey * ey) ** 0.5
        if L < 1e-4:
            return tri
        n.append((sgn * ey / L, -sgn * ex / L))
    out = []
    for i in range(3):
        p = (i + 2) % 3
        k = max(0.25, 1.0 + n[p][0] * n[i][0] + n[p][1] * n[i][1])
        out.append((P[i][0] + d * (n[p][0] + n[i][0]) / k, P[i][1] + d * (n[p][1] + n[i][1]) / k))
    return out


def crack_area(frame, rule):
    tris = []
    for i in range(0, len(frame) - 2, 3):
        raw = [(v[0], v[1]) for v in frame[i:i + 3]]
        tri = [(x / F, y / F) for x, y in raw]
        whole = any((x & 0xFFFF) == 0 and (y & 0xFFFF) == 0 for x, y in raw)
        tris.append(grow(tri, rule(whole)))
    xs = [p[0] for t in tris for p in t]
    ys = [p[1] for t in tris for p in t]
    # the visible frame: clamp to a generous window around the screen
    x0, x1 = max(min(xs), -80.0), min(max(xs), 420.0)
    y0, y1 = max(min(ys), -20.0), min(max(ys), 520.0)
    W, H = int((x1 - x0) * S) + 2, int((y1 - y0) * S) + 2
    im = Image.new("1", (W, H), 0)
    d = ImageDraw.Draw(im)
    for t in tris:
        d.polygon([((x - x0) * S, (y - y0) * S) for x, y in t], fill=1)
    m = np.array(im, dtype=bool)
    r = int(0.75 * S)                      # closes anything up to 1.5 px wide
    st = ndimage.generate_binary_structure(2, 1)
    closed = ndimage.binary_erosion(ndimage.binary_dilation(m, st, iterations=r), st, iterations=r,
                                    border_value=1)
    thin = closed & ~m
    return thin.sum() / float(S * S)


def evaluate(a):
    data = json.load(open(a[1]))
    frames = [[tuple(v) for v in f] for f in data.values()]
    rules = [("no fill", lambda w: 0.0),
             ("0.35 (current)", lambda w: 0.35),
             ("0.50", lambda w: 0.5),
             ("0.75", lambda w: 0.75),
             ("adaptive 0.35 / 0.75 clipped", lambda w: 0.75 if w else 0.35),
             ("adaptive 0.35 / 1.00 clipped", lambda w: 1.0 if w else 0.35),
             ("adaptive 0.50 / 1.00 clipped", lambda w: 1.0 if w else 0.5)]
    print("%d frames; thin uncovered area inside the scene, native px^2 per frame" % len(frames))
    for name, rule in rules:
        areas = [crack_area(f, rule) for f in frames]
        print("   %-30s mean %7.2f   worst frame %7.2f" % (name, sum(areas) / len(areas), max(areas)))


if __name__ == "__main__":
    if sys.argv[1] == "capture":
        capture(sys.argv[2:])
    else:
        evaluate(sys.argv[1:])
