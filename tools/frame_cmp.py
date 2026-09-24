#!/usr/bin/env python3
"""Record a draw frame, an empty frame, and a control draw frame; save the
access logs and report the first game-side divergence for
draw-vs-empty and draw-vs-draw (control for state drift)."""
import json
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4630
PAGES = int(sys.argv[2]) if len(sys.argv) > 2 else 8


def cur_frame(port):
    return send(port, '{"cmd":"frame"}')["frame"]


def draws(port, f):
    r = send(port, '{"cmd":"gpu_frame_dump","frame":%d,"count":4}' % f)
    return r.get("count", 0) > 0


def record(port, frame):
    send(port, '{"cmd":"record_frame","frame":%d}' % frame)
    t0 = time.time()
    while time.time() - t0 < 8.0:
        if cur_frame(port) > frame + 3:
            break
        time.sleep(0.02)
    entries = []
    for p in range(PAGES * 3):
        d = send(port, '{"cmd":"record_frame_dump","offset":%d,"count":1500}' % (p * 1500))
        ev = d.get("entries", [])
        entries.extend(ev)
        if len(ev) < 1500:
            break
    return entries


def game(entries):
    """Drop BIOS work-RAM noise: keep accesses from the game's own code."""
    out = []
    for e in entries:
        pc = int(e["pc"], 16)
        if pc >= 0x80010000:
            out.append(e)
    return out


def first_diff(a, b, label):
    n = min(len(a), len(b))
    for i in range(n):
        x, y = a[i], b[i]
        if (x["kind"], x["addr"], x["val"], x["pc"]) != (y["kind"], y["addr"], y["val"], y["pc"]):
            print("== %s: first divergence at %d/%d" % (label, i, n))
            for j in range(max(0, i - 3), min(n, i + 5)):
                m = " *" if j == i else "  "
                p, q = a[j], b[j]
                print("%s[%d] A %s %s=%s pc=%s" % (m, j, p["kind"], p["addr"], p["val"], p["pc"]))
                print("%s[%d] B %s %s=%s pc=%s" % (m, j, q["kind"], q["addr"], q["val"], q["pc"]))
            return i
    print("== %s: no divergence in %d entries" % (label, n))
    return None


def main():
    f = cur_frame(PORT)
    par = {}
    for fr in range(f - 6, f - 1):
        par[fr % 2] = par.get(fr % 2, draws(PORT, fr))
    draw_par = 1 if par.get(1) else 0
    empty_par = 1 - draw_par
    print("current frame %d, draw parity %d" % (f, draw_par))

    def next_frame(parity, lead=60):
        t = cur_frame(PORT) + lead
        if t % 2 != parity:
            t += 1
        return t

    d1f = next_frame(draw_par)
    d1 = record(PORT, d1f)
    ef = next_frame(empty_par)
    e = record(PORT, ef)
    d2f = next_frame(draw_par)
    d2 = record(PORT, d2f)
    print("frames: draw %d (%d), empty %d (%d), draw %d (%d)"
          % (d1f, len(d1), ef, len(e), d2f, len(d2)))
    print("classes: draw=%s empty=%s" % (draws(PORT, d1f), draws(PORT, ef)))

    json.dump({"frame": d1f, "entries": d1}, open("logs/frame_d1.json", "w"))
    json.dump({"frame": ef, "entries": e}, open("logs/frame_e.json", "w"))
    json.dump({"frame": d2f, "entries": d2}, open("logs/frame_d2.json", "w"))

    first_diff(game(d1), game(e), "draw vs empty")
    first_diff(game(d1), game(d2), "draw vs draw (control)")


if __name__ == "__main__":
    main()
