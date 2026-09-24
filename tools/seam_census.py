#!/usr/bin/env python3
"""Count cracks between polygons, from the renderer's own vertex stream.

Usage: python tools/seam_census.py [--frames 40] [--hold left] [--radius 0.9]
                                   [--samples 6] [--label text]

Arms the GPU seam census (debug verb "seam_dump", runtime patch 014) and, for a
number of guest frames, reads every triangle vertex with the position the
renderer uses (16.16 sub-pixel, or the whole pixel for an untracked vertex) and
its provenance: 0 native, 1 position-cache fallback, 2 dataflow.

In a watertight mesh, vertices shared between polygons are bit-identical. Two
vertex positions closer than --radius pixels that are NOT identical are a crack
(or a T-junction). Reported per frame on average, split by the provenance pair
that forms them, which says which path to fix.
"""
import collections
import csv
import json
import os
import sys
import time

from ask import ask
from input_probe import BUTTONS

PORT = 4624
SRC = {0: "native", 1: "fallback", 2: "dataflow"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def q(**k):
    return ask(PORT, json.dumps(k), timeout=20.0, tries=2)


def read_frame(path):
    r = q(cmd="seam_dump", path=path)
    if not r.get("ok") or not r.get("vertices"):
        return None, []
    rows = []
    frame = None
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            frame = int(row["frame"])
            rows.append((int(row["x16"]), int(row["y16"]), int(row["src"]), int(row["prim"]),
                         row["addr"], row["word"]))
    return frame, rows


def cracks(rows, radius16):
    # distinct positions, keep the best provenance seen at each
    pos = {}
    for x, y, src, prim, addr, word in rows:
        k = (x, y)
        if k not in pos or src > pos[k][0]:
            pos[k] = (src, prim, addr, word)
    cells = collections.defaultdict(list)
    for (x, y) in pos:
        cells[(x >> 16, y >> 16)].append((x, y))
    out = []
    r2 = radius16 * radius16
    for (cx, cy), pts in cells.items():
        near = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near.extend(cells.get((cx + dx, cy + dy), ()))
        for a in pts:
            for b in near:
                if a < b:
                    d2 = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
                    if d2 < r2:
                        out.append((a, b, d2 ** 0.5 / 65536.0, pos[a], pos[b]))
    return out, len(pos)


def tjunctions(rows, min_edge_px=6.0, max_gap_px=0.75, smallest=False):
    """Vertices lying just beside another triangle's long edge: the geometric
    signature of a visible crack. Rows come three per triangle. Returns
    (gap_px, vertex_row, edge_len_px) per finding, largest gap per vertex."""
    F = 65536.0
    pts = {}
    for r in rows:
        k = (r[0], r[1])
        if k not in pts or r[2] > pts[k][2]:
            pts[k] = r
    plist = [(x / F, y / F, k) for k, (x, y) in ((k, k) for k in pts)]
    edges = set()
    for i in range(0, len(rows) - 2, 3):
        t = [(rows[i + j][0], rows[i + j][1]) for j in range(3)]
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            if a != b:
                edges.add((a, b) if a < b else (b, a))
    found = {}
    for a, b in edges:
        ax, ay, bx, by = a[0] / F, a[1] / F, b[0] / F, b[1] / F
        ex, ey = bx - ax, by - ay
        L2 = ex * ex + ey * ey
        if L2 < min_edge_px * min_edge_px:
            continue
        L = L2 ** 0.5
        lo_x, hi_x = min(ax, bx) - 1, max(ax, bx) + 1
        lo_y, hi_y = min(ay, by) - 1, max(ay, by) + 1
        for px, py, k in plist:
            if px < lo_x or px > hi_x or py < lo_y or py > hi_y or k == a or k == b:
                continue
            t = ((px - ax) * ex + (py - ay) * ey) / L2
            if t <= 0.03 or t >= 0.97:
                continue
            d = abs((px - ax) * ey - (py - ay) * ex) / L
            if 1e-4 < d < max_gap_px:
                best = found.get(k)
                if best is None or (d < best[0] if smallest else d > best[0]):
                    found[k] = (d, pts[k], L)
    return list(found.values())


def main():
    a = sys.argv[1:]
    frames = int(a[a.index("--frames") + 1]) if "--frames" in a else 40
    radius = float(a[a.index("--radius") + 1]) if "--radius" in a else 0.9
    nsamp = int(a[a.index("--samples") + 1]) if "--samples" in a else 6
    label = a[a.index("--label") + 1] if "--label" in a else ""
    mask = 0xFFFF
    if "--hold" in a:
        for b in a[a.index("--hold") + 1].split(","):
            mask &= ~BUTTONS[b]
    path = os.path.join(ROOT, "logs", "seam_frame.csv").replace(os.sep, "/")
    q(cmd="seam_dump", path=path)          # arm
    q(cmd="set_input", buttons=mask)
    time.sleep(0.5)
    seen = set()
    pair_kinds = collections.Counter()
    src_share = collections.Counter()
    total_cracks = total_pos = total_verts = 0
    samples = []
    tj_total = 0
    tj_gap = 0.0
    tj_kinds = collections.Counter()
    tj_samples = []
    tj_orig = 0
    hist = collections.Counter()
    end = time.time() + 30
    while len(seen) < frames and time.time() < end:
        frame, rows = read_frame(path)
        if frame is None or frame in seen:
            time.sleep(0.01)
            continue
        seen.add(frame)
        cr, npos = cracks(rows, radius * 65536.0)
        total_cracks += len(cr)
        total_pos += npos
        total_verts += len(rows)
        for r in rows:
            src_share[r[2]] += 1
        # The same frame as stock hardware would place it (whole pixels).
        tj_orig += len(tjunctions([(r[0] & ~0xFFFF, r[1] & ~0xFFFF) + r[2:] for r in rows]))
        # Gap-size distribution: per vertex, the NEAREST long edge it is not part
        # of, up to 2 px away.
        for d, row, elen in tjunctions(rows, max_gap_px=2.0, smallest=True):
            hist[min(7, int(d / 0.25))] += 1
        for d, row, elen in tjunctions(rows):
            tj_total += 1
            tj_gap += d
            whole = (row[0] & 0xFFFF) == 0 and (row[1] & 0xFFFF) == 0
            tj_kinds[(SRC[row[2]], 'whole-pixel' if whole else 'sub-pixel')] += 1
            if len(tj_samples) < nsamp:
                tj_samples.append((d, row, elen))
        for pa, pb, dist, ia, ib in cr:
            pair_kinds[tuple(sorted((SRC[ia[0]], SRC[ib[0]])))] += 1
            if len(samples) < nsamp:
                samples.append((pa, pb, dist, ia, ib))
    q(cmd="clear_input")
    n = max(1, len(seen))
    tv = max(1, total_verts)
    print("%s frames %d | vertices/frame %.0f (dataflow %.1f%% fallback %.1f%% native %.1f%%) | "
          "distinct positions/frame %.0f | CRACK PAIRS/frame %.1f" % (
              (label + " ") if label else "", len(seen), total_verts / n,
              100.0 * src_share[2] / tv, 100.0 * src_share[1] / tv, 100.0 * src_share[0] / tv,
              total_pos / n, total_cracks / n))
    print("   EDGE CRACKS (vertex beside another polygon's long edge): %.1f per frame, mean gap %.3f px" % (
        tj_total / n, tj_gap / max(1, tj_total)))
    print("      (same frames on whole pixels, as the original renders them: %.1f per frame)" % (tj_orig / n))
    print("      nearest-edge gap histogram per frame: " + "  ".join(
        "%.2f-%.2f:%.1f" % (b * 0.25, b * 0.25 + 0.25, hist[b] / n) for b in range(8)))
    for kind, c in tj_kinds.most_common():
        print("      %-10s %-12s %.1f per frame" % (kind[0], kind[1], c / n))
    for d, row, elen in tj_samples:
        print("      e.g. (%.3f,%.3f) %s prim %02X @%s word %s  gap %.3f px beside a %.0f px edge" % (
            row[0] / 65536.0, row[1] / 65536.0, SRC[row[2]], row[3], row[4], row[5], d, elen))
    for kind, c in pair_kinds.most_common():
        print("   %-20s %.1f per frame" % ("%s-%s" % kind, c / n))
    for pa, pb, dist, ia, ib in samples:
        print("   e.g. (%.3f,%.3f) %s prim %02X @%s  vs  (%.3f,%.3f) %s prim %02X @%s  dist %.3f px" % (
            pa[0] / 65536.0, pa[1] / 65536.0, SRC[ia[0]], ia[1], ia[2],
            pb[0] / 65536.0, pb[1] / 65536.0, SRC[ib[0]], ib[1], ib[2], dist))


if __name__ == "__main__":
    main()
