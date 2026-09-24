#!/usr/bin/env python3
"""Correlate a native-wide present capture with a ws_census dump.

Usage: python tools/void_report.py <shot.png> <census.csv>
              [--present-w 426] [--offset 53] [--band 0.2,0.95]

The shot is the composed present of a native-wide frame (present width
disp_w+2*offset mapped across the image). The census records every drawn
primitive with its pre-draw_offset screen-X extent across a frame window.

For each image column we measure how many pixels are NOT background (sky).
Columns that are almost all background are "void" (no geometry drawn). We map
each column back to pre-offset screen X and compare against the terrain prims
the engine actually submitted. This separates:
  * engine did not submit geometry there  -> authored world edge / cull
  * engine submitted it but nothing drew  -> compositor / clip problem
"""
import argparse
import csv
import sys

import numpy as np
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shot")
    ap.add_argument("census")
    ap.add_argument("--present-w", type=int, default=426)
    ap.add_argument("--offset", type=int, default=53)
    ap.add_argument("--band", default="0.2,0.95",
                    help="vertical band of the image to analyse (fractions)")
    ap.add_argument("--bg-dist", type=float, default=60.0)
    ap.add_argument("--void-frac", type=float, default=0.06)
    args = ap.parse_args()

    img = np.asarray(Image.open(args.shot).convert("RGB"), dtype=np.int16)
    h, w, _ = img.shape
    y0f, y1f = (float(x) for x in args.band.split(","))
    y0, y1 = int(h * y0f), int(h * y1f)
    band = img[y0:y1]

    # Background = the sky colour. Prefer the median of the top rows (the sky
    # is at the top of an exterior view); fall back to the band's modal colour
    # for scenes whose top is not a near-uniform plate (interiors, fades).
    top_rows = band[: max(1, band.shape[0] // 12)]
    top_med = np.median(top_rows.reshape(-1, 3), axis=0)
    top_spread = np.abs(top_rows - top_med).mean()
    if top_spread < 12.0:
        bg = top_med
    else:
        flat = band.reshape(-1, 3)
        colours, counts = np.unique(flat, axis=0, return_counts=True)
        bg = colours[counts.argmax()]

    dist = np.abs(band - bg).sum(axis=2)
    nonbg = (dist > args.bg_dist)
    frac = nonbg.mean(axis=0)          # per image column

    print(f"image {w}x{h}; band y {y0}..{y1}; bg RGB {tuple(int(v) for v in bg)}")
    print(f"void columns (non-bg frac < {args.void_frac}):")
    col_x = (np.arange(w) + 0.5) / w * args.present_w - args.offset
    void = frac < args.void_frac
    runs = []
    i = 0
    while i < w:
        if void[i]:
            j = i
            while j + 1 < w and void[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    if not runs:
        print("  none")
    for a, b in runs:
        print(f"  image x {a:4d}..{b:4d}  -> pre-offset x "
              f"{col_x[a]:7.1f}..{col_x[min(b, w-1)]:7.1f}  "
              f"({b - a + 1} cols, frac_min {frac[a:b + 1].min():.3f})")

    # Census terrain coverage.
    polys = []
    with open(args.census, newline="") as fh:
        for r in csv.DictReader(fh):
            if int(r["tagged"]) == 0 and r["opcode"].lower() in ("0x3c", "0x3e", "0x3d", "0x3f"):
                polys.append((int(r["xmin"]), int(r["xmax"])))
    if polys:
        lo = min(a for a, b in polys)
        hi = max(b for a, b in polys)
        print(f"census untagged terrain polys: {len(polys)}; x extent {lo}..{hi}")
        for a, b in runs:
            xa = col_x[a]
            xb = col_x[min(b, w - 1)]
            n = sum(1 for pa, pb in polys if pb >= xa and pa <= xb)
            print(f"  void x {xa:7.1f}..{xb:7.1f}: {n} census polys overlap")
    else:
        print("census: no untagged terrain polys")


if __name__ == "__main__":
    sys.exit(main())
