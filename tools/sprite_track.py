#!/usr/bin/env python3
"""Measure how billboard sprites move against the terrain while the view turns.

Usage: python tools/sprite_track.py [logs/sprite_frames.json]
       (capture while turning: --dx 1; while walking: --dx 0 --hold up)
Input: a capture made by tools/sprite_capture.py in the off-screen GL run
(tools/seam_run.ps1 -Slot N -NoCensus -Py "tools/sprite_capture.py").

Sprites are the GP0 0x2C-0x2F quads, terrain the 0x3C quads. Sprites and
terrain vertices are followed from frame to frame by continuity (packet
addresses are no identity: the visible set changes while turning). Under a pure
turn every screen point is a smooth function of the view angle, so a sprite
coordinate is a smooth function of a nearby terrain vertex's x. A cubic is
fitted over a sliding window and the residual is the sprite's motion against
the ground, in native pixels. Terrain against terrain gives the method's floor.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def polyfit_resid(xs, ys, deg=3):
    n = deg + 1
    mx = sum(xs) / len(xs)
    sx = max(1e-9, max(abs(x - mx) for x in xs))
    t = [(x - mx) / sx for x in xs]
    A = [[sum(ti ** (r + c) for ti in t) for c in range(n)] for r in range(n)]
    b = [sum(y * ti ** r for ti, y in zip(t, ys)) for r in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]
        b[i], b[p] = b[p], b[i]
        if abs(A[i][i]) < 1e-12:
            return None
        for r in range(i + 1, n):
            f = A[r][i] / A[i][i]
            for c in range(i, n):
                A[r][c] -= f * A[i][c]
            b[r] -= f * b[i]
    co = [0.0] * n
    for i in range(n - 1, -1, -1):
        co[i] = (b[i] - sum(A[i][c] * co[c] for c in range(i + 1, n))) / A[i][i]
    return [y - sum(co[k] * ti ** k for k in range(n)) for ti, y in zip(t, ys)]


def split(rows):
    """-> (sprite quads [(x0,y0,x1,y1)], terrain points {(x,y)})"""
    quads, pts, i = [], set(), 0
    while i < len(rows):
        r = rows[i]
        if 0x2C <= r[3] <= 0x2F and i + 5 < len(rows) and rows[i + 5][3] == r[3]:
            p = rows[i:i + 6]
            xs, ys = [v[0] for v in p], [v[1] % 240.0 for v in p]
            quads.append((min(xs), min(ys), max(xs), max(ys)))
            i += 6
            continue
        if r[3] == 0x3C:
            pts.add((r[0], r[1] % 240.0))
        i += 1
    return quads, list(pts)


def nearest(pts, x, y):
    best, bd = None, 1e9
    for p in pts:
        d = (p[0] - x) ** 2 + (p[1] - y) ** 2
        if d < bd:
            best, bd = p, d
    return best, bd ** 0.5


def stats(name, ref, val):
    out = []
    W = 24                                   # sliding window, frames
    for s in range(0, len(ref) - W + 1, W // 2):
        r = polyfit_resid(ref[s:s + W], val[s:s + W])
        if r:
            out.extend(r)
    if not out:
        return
    rms = (sum(e * e for e in out) / len(out)) ** 0.5
    print("      %-22s resid rms %.3f px, max %.3f px" % (name, rms, max(abs(e) for e in out)))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "logs", "sprite_frames.json")
    F = [split(f["rows"]) for f in json.load(open(path))]
    print("frames: %d" % len(F))
    # Sprites drawn beyond the 4:3 range: only possible with the widened
    # sprite frustum test (game.toml ws-sprite-*).
    beyond = sum(1 for quads, _ in F for k in quads if k[2] - k[0] >= 8 and (k[0] < -2 or k[2] > 322))
    outside = sum(1 for quads, _ in F for k in quads if k[2] - k[0] >= 8 and (k[2] < 0 or k[0] > 320))
    print("sprite quads reaching past the 4:3 edges: %d, centre-side fully outside 0..320: %d" % (beyond, outside))
    frac_w = sum(1 for quads, _ in F for k in quads if abs((k[2] - k[0]) - round(k[2] - k[0])) > 0.01)
    total = sum(len(quads) for quads, _ in F)
    print("sprite quads with a fractional width: %d of %d" % (frac_w, total))
    for q0 in F[0][0]:
        if q0[2] - q0[0] < 16:
            continue
        # follow the sprite by its centre
        track, cur = [], q0
        for quads, _ in F:
            cx, cy = (cur[0] + cur[2]) / 2, (cur[1] + cur[3]) / 2
            c = min(quads, key=lambda k: ((k[0] + k[2]) / 2 - cx) ** 2 + ((k[1] + k[3]) / 2 - cy) ** 2,
                    default=None)
            if c is None or abs((c[0] + c[2]) / 2 - cx) > 20:
                break
            track.append(c)
            cur = c
        n = len(track)
        print("sprite at (%.1f,%.1f)-(%.1f,%.1f): followed %d frames, moved %.1f px, width %g..%g" % (
            q0[0], q0[1], q0[2], q0[3], n, track[-1][0] - track[0][0],
            min(t[2] - t[0] for t in track), max(t[2] - t[0] for t in track)))
        whole = sum(1 for t in track if t[0] == int(t[0]) and t[1] == int(t[1]))
        print("      frames on whole pixels: %d" % whole)
        # reference terrain vertices near the sprite's foot, followed by continuity
        fx, fy = (q0[0] + q0[2]) / 2, q0[3]
        seeds = sorted(F[0][1], key=lambda p: (p[0] - fx) ** 2 + (p[1] - fy) ** 2)[:6]
        refs = []
        for sd in seeds:
            tr, p = [sd], sd
            for i in range(1, n):
                dxs = (track[i][0] + track[i][2]) / 2 - (track[i - 1][0] + track[i - 1][2]) / 2
                c, d = nearest(F[i][1], p[0] + dxs, p[1])
                if c is None or d > 3.0:
                    break
                tr.append(c)
                p = c
            if len(tr) == n:
                refs.append(tr)
        print("      terrain reference vertices followed all the way: %d of %d" % (len(refs), len(seeds)))
        if not refs:
            continue
        ref = refs[0]
        # abscissa: whichever reference coordinate moves more (x when turning
        # or strafing, y when walking forward)
        rx = [p[0] for p in ref]
        ry_ = [p[1] for p in ref]
        if max(ry_) - min(ry_) > max(rx) - min(rx):
            rx = ry_
        print("      reference vertex moved %.1f px" % (max(rx) - min(rx)))
        stats("sprite centre x", rx, [(t[0] + t[2]) / 2 for t in track])
        stats("sprite left x", rx, [t[0] for t in track])
        stats("sprite right x", rx, [t[2] for t in track])
        stats("sprite centre y", rx, [(t[1] + t[3]) / 2 for t in track])
        stats("sprite bottom y (foot)", rx, [t[3] for t in track])
        stats("sprite top y", rx, [t[1] for t in track])
        for o in refs[1:3]:
            stats("terrain vertex x (floor)", rx, [p[0] for p in o])
            stats("terrain vertex y (floor)", rx, [p[1] for p in o])


if __name__ == "__main__":
    main()
