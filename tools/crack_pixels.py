#!/usr/bin/env python3
"""Pixel-level crack count in a supersampled capture.

Usage: python tools/crack_pixels.py image.png [more.png ...] [--diff a.png b.png out.png]

A crack between polygons shows up as a 1-3 px wide line whose colour differs
sharply from BOTH sides while the two sides agree with each other. Counts such
pixels (horizontal and vertical test, widths 1..3) inside the game picture.
"""
import sys

from PIL import Image, ImageChops


def count(path, thr=60, agree=28):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    n = 0

    def far(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])

    x0, x1 = int(w * 0.03), int(w * 0.97)
    for y in range(4, h - 4):
        for x in range(max(4, x0), min(w - 4, x1)):
            c = px[x, y]
            hit = False
            for wd in (1, 2, 3):
                l, r = px[x - 1, y], px[x + wd, y]
                if far(l, r) < agree and far(c, l) > thr and far(px[x + wd - 1, y], r) > thr:
                    hit = True
                    break
                u, d = px[x, y - 1], px[x, y + wd]
                if far(u, d) < agree and far(c, u) > thr and far(px[x, y + wd - 1], d) > thr:
                    hit = True
                    break
            n += hit
    return n


def main():
    a = sys.argv[1:]
    if "--diff" in a:
        i = a.index("--diff")
        p, q, out = a[i + 1:i + 4]
        d = ImageChops.difference(Image.open(p).convert("RGB"), Image.open(q).convert("RGB"))
        d = d.point(lambda v: min(255, v * 4))
        d.save(out)
        print("diff saved", out)
        a = a[:i]
    for p in a:
        print("%-40s crack-like pixels: %d" % (p, count(p)))


if __name__ == "__main__":
    main()
