#!/usr/bin/env python3
"""Sprite against ground while walking (view bob included).

Usage: python tools/sprite_walk_track.py [logs/sprite_frames_walk.json]
Input: tools/sprite_capture.py --dx 0 --hold down --sleep 0 (off-screen GL run).

A body lies at a fixed spot of the ground, so the screen distance from its foot
to a ground vertex next to it changes smoothly with the guest frame number even
with the view bobbing. A cubic is fitted to that distance over windows of 16
samples; the residual is the sprite's motion against the ground. The same for
two ground vertices gives the method's floor. Also counts sprite quads whose
size is a whole number of pixels (size not carried by the scalar tier).
"""
import json
import os
import sys

from sprite_track import nearest, polyfit_resid, split

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resid(t, v, W=16):
    out = []
    for s in range(0, len(t) - W + 1, W // 2):
        r = polyfit_resid(t[s:s + W], v[s:s + W])
        if r:
            out += r
    if not out:
        return 0.0, 0.0
    return (sum(e * e for e in out) / len(out)) ** .5, max(abs(e) for e in out)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "logs", "sprite_frames_walk.json")
    raw = json.load(open(path))
    t = [float(f["frame"]) for f in raw]
    F = [split(f["rows"]) for f in raw]
    print("frames: %d" % len(F))
    for q0 in [q for q in F[0][0] if q[2] - q[0] > 16]:
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
        moving = [i for i in range(1, n) if track[i] != track[i - 1]]
        whole = sum(1 for i in moving if track[i][2] - track[i][0] == round(track[i][2] - track[i][0]))
        print("sprite at (%.1f,%.1f): followed %d frames, width %.2f..%.2f, whole-pixel size in %d of %d moving frames" % (
            q0[0], q0[1], n, min(k[2] - k[0] for k in track), max(k[2] - k[0] for k in track), whole, len(moving)))
        fx, fy = (q0[0] + q0[2]) / 2, q0[3]
        refs = []
        for sd in sorted(F[0][1], key=lambda p: (p[0] - fx) ** 2 + (p[1] - fy) ** 2)[:10]:
            tr, p, ok = [sd], sd, True
            for i in range(1, n):
                c, d = nearest(F[i][1], p[0] + ((track[i][0] + track[i][2]) - (track[i - 1][0] + track[i - 1][2])) / 2,
                               p[1] + track[i][3] - track[i - 1][3])
                if c is None or d > 3:
                    ok = False
                    break
                tr.append(c)
                p = c
            if ok:
                refs.append(tr)
        for tr in refs[:3]:
            dx = [(a[0] + a[2]) / 2 - b[0] for a, b in zip(track, tr)]
            dy = [a[3] - b[1] for a, b in zip(track, tr)]
            print("   foot vs ground   x rms %.3f max %.3f | y rms %.3f max %.3f" % (resid(t[:n], dx) + resid(t[:n], dy)))
        if len(refs) >= 2:
            a, b = refs[0], refs[1]
            print("   ground vs ground x rms %.3f max %.3f | y rms %.3f max %.3f" % (
                resid(t[:n], [p[0] - q[0] for p, q in zip(a, b)]) + resid(t[:n], [p[1] - q[1] for p, q in zip(a, b)])))


if __name__ == "__main__":
    main()
