#!/usr/bin/env python3
"""Find object (sprite) quads in a still view and the game code that builds them.

Usage: python tools/object_quads.py            (static view, no input)

All world prims in Disruptor are GP0 0x3C quads, terrain and objects alike. They
are told apart here by texture: packets are read back from guest RAM and grouped
by (texture page, CLUT, tile rectangle). Terrain uses 32x32 tiles from a few
pages and CLUTs many times over; an object uses its own sprite sheet rectangle,
usually not 32x32. For every group that is not a 32x32 tile the screen rectangle
is printed, and the write trace reports which PCs store those packets' vertex
words - i.e. the routine that positions the object on screen.
"""
import collections
import csv
import json
import os
import time

from ask import ask

PORT = 4624
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def q(**k):
    return ask(PORT, json.dumps(k), timeout=30.0, tries=2)


def read_words(addr, n):
    r = q(cmd="read_ram", addr="0x%08X" % (0x80000000 | addr), len=n * 4)
    raw = bytes.fromhex(r.get("hex") or r.get("data") or "")
    return [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw) - 3, 4)]


def sx(w):
    x = w & 0x7FF
    return x - 0x800 if x & 0x400 else x


def sy(w):
    y = (w >> 16) & 0x7FF
    return y - 0x800 if y & 0x400 else y


def main():
    path = os.path.join(ROOT, "logs", "seam_frame.csv").replace(os.sep, "/")
    q(cmd="clear_input")
    q(cmd="seam_dump", path=path)
    time.sleep(1.0)
    q(cmd="seam_dump", path=path)
    rows = list(csv.DictReader(open(path, newline="")))
    bases = sorted({(int(rows[i]["addr"], 16) - 4) & 0x1FFFFC
                    for i in range(0, len(rows) - 2, 3)
                    if int(rows[i]["prim"]) == 0x3C and int(rows[i]["addr"], 16) != 0xFFFFFFFF})
    groups = collections.defaultdict(list)
    for b in bases:
        w = read_words(b, 12)
        if len(w) != 12 or (w[0] >> 24) != 0x3C:
            continue
        us = [w[i] & 0xFF for i in (2, 5, 8, 11)]
        vs = [(w[i] >> 8) & 0xFF for i in (2, 5, 8, 11)]
        tile = (max(us) - min(us) + 1, max(vs) - min(vs) + 1)
        key = ((w[5] >> 16) & 0x1FF, (w[2] >> 16) & 0xFFFF, min(us), min(vs), tile)
        xs = [sx(w[i]) for i in (1, 4, 7, 10)]
        ys = [sy(w[i]) for i in (1, 4, 7, 10)]
        groups[key].append((b, min(xs), min(ys), max(xs), max(ys)))
    print("quads read back: %d of %d, texture groups: %d" % (
        sum(len(v) for v in groups.values()), len(bases), len(groups)))
    # Group every quad by the code site that stored its first vertex word.
    allq = {b: (x0, y0, x1, y1, key) for key, qs in groups.items() for b, x0, y0, x1, y1 in qs}
    lo, hi = min(allq), max(allq) + 48
    q(cmd="wtrace_del")
    print("write trace armed:", q(cmd="wtrace_range", lo="0x%X" % lo, hi="0x%X" % hi).get("ok"))
    time.sleep(1.0)
    d = q(cmd="wtrace_dump", count=60000, newest=1)
    q(cmd="wtrace_del")
    first_vertex = {b + 4: b for b in allq}
    site = {}
    for e in d.get("entries", d.get("events", [])):
        a = e.get("addr")
        a = (int(a, 16) if isinstance(a, str) else int(a or 0)) & 0x1FFFFF
        if a in first_vertex:
            site[first_vertex[a]] = e.get("pc")
    by_pc = collections.defaultdict(list)
    for b, pc in site.items():
        by_pc[pc].append(b)
    print("quads with a traced writer: %d of %d" % (len(site), len(allq)))
    for pc, bs in sorted(by_pc.items(), key=lambda kv: len(kv[1])):
        rects = [allq[b][:4] for b in bs]
        tiles = collections.Counter(allq[b][4][4] for b in bs)
        pages = collections.Counter(allq[b][4][0] for b in bs)
        print("   writer %s: %3d quads | tile sizes %s | tpages %s" % (
            pc, len(bs), dict(tiles.most_common(3)), {("%03X" % k): v for k, v in pages.most_common(4)}))
        for r in rects[:4]:
            print("        screen (%d,%d)-(%d,%d)" % r)


if __name__ == "__main__":
    main()
