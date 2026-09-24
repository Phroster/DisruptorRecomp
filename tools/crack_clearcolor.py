#!/usr/bin/env python3
"""Count hairline cracks that let the background clear colour show through.

Usage: python tools/crack_clearcolor.py a.png [b.png ...] [--mark out.png]

Takes the clear colour from the largest flat region at the picture's edge
columns (or --color r,g,b), then counts pixels of that colour that are THIN:
non-clear pixels within 3 px on both sides horizontally or vertically. Large
clear areas (a missing backdrop) are not counted. --mark saves the first image
with the hits circled in red.
"""
import sys

from PIL import Image, ImageDraw


def near(c, k, tol=40):
    return abs(c[0] - k[0]) + abs(c[1] - k[1]) + abs(c[2] - k[2]) < tol


def thin_hits(im, key):
    w, h = im.size
    px = im.load()
    hits = []
    for y in range(6, h - 6):
        for x in range(6, w - 6):
            if not near(px[x, y], key):
                continue
            lh = any(not near(px[x - d, y], key) for d in (1, 2, 3))
            rh = any(not near(px[x + d, y], key) for d in (1, 2, 3))
            uv = any(not near(px[x, y - d], key) for d in (1, 2, 3))
            dv = any(not near(px[x, y + d], key) for d in (1, 2, 3))
            if (lh and rh) or (uv and dv):
                hits.append((x, y))
    # Textures and HUD digits of a similar colour form dense blobs; a crack is a
    # sparse line. Drop every hit that has many other hits in its 80 px cell.
    import collections
    cell = collections.Counter((x // 80, y // 80) for x, y in hits)
    return [(x, y) for x, y in hits if cell[(x // 80, y // 80)] <= 60]


def main():
    a = sys.argv[1:]
    mark = None
    if "--mark" in a:
        i = a.index("--mark"); mark = a[i + 1]; a = a[:i] + a[i + 2:]
    key = None
    if "--color" in a:
        i = a.index("--color"); key = tuple(int(v) for v in a[i + 1].split(",")); a = a[:i] + a[i + 2:]
    for n, p in enumerate(a):
        im = Image.open(p).convert("RGB")
        k = key
        if k is None:
            from collections import Counter
            w, h = im.size
            c = Counter(im.crop((int(w * 0.03), 0, int(w * 0.97), h)).resize((256, 135)).getdata())
            k = max((col for col, _ in c.most_common(12)), key=lambda col: max(col) - min(col))
        hits = thin_hits(im, k)
        print("%-32s clear colour %s  thin clear-colour pixels: %d" % (p, k, len(hits)))
        if mark and n == 0:
            d = ImageDraw.Draw(im)
            for x, y in hits[::3]:
                d.ellipse((x - 9, y - 9, x + 9, y + 9), outline=(255, 0, 0))
            im.save(mark)


if __name__ == "__main__":
    main()
