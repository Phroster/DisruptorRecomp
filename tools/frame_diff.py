#!/usr/bin/env python3
"""Record two consecutive frames (draw vs empty) and find the first divergent
access - that is literally the branch that gates the 30 fps render cadence."""
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
    r = send(port, '{"cmd":"record_frame","frame":%d}' % frame)
    print("arm:", r)
    t0 = time.time()
    while time.time() - t0 < 8.0:
        if cur_frame(port) > frame + 3:
            break
        time.sleep(0.02)
    entries = []
    total = overflow = 0
    for p in range(PAGES):
        d = send(port, '{"cmd":"record_frame_dump","offset":%d,"count":4000}' % (p * 4000))
        ev = d.get("entries", [])
        entries.extend(ev)
        total = d.get("total", 0)
        overflow = d.get("overflow", 0)
        if len(ev) < 4000:
            break
    return entries, total, overflow


def main():
    f = cur_frame(PORT)
    par = {}
    for fr in range(f - 6, f - 1):
        par[fr % 2] = par.get(fr % 2, draws(PORT, fr))
    draw_par = 1 if par.get(1) else 0
    empty_par = 1 - draw_par
    print("current frame %d, draw parity %d" % (f, draw_par))

    base = f + 60
    if base % 2 != draw_par:
        base += 1
    target_d = base
    print("recording draw frame %d" % target_d)
    d_ev, d_tot, d_ovf = record(PORT, target_d)
    f2 = cur_frame(PORT)
    target_e = f2 + 60
    if target_e % 2 != empty_par:
        target_e += 1
    print("recording empty frame %d (from %d)" % (target_e, f2))
    e_ev, e_tot, e_ovf = record(PORT, target_e)
    d_draw = draws(PORT, target_d)
    e_draw = draws(PORT, target_e)
    print("frame %d drew=%s (%d entries), frame %d drew=%s (%d entries)"
          % (target_d, d_draw, d_tot, target_e, e_draw, e_tot))
    if d_draw == e_draw:
        print("both frames same class; retry might help")
        return
    if not d_ev or not e_ev:
        print("missing entries (arm too late)")
        return

    n = min(len(d_ev), len(e_ev))
    first = None
    for i in range(n):
        a, b = d_ev[i], e_ev[i]
        if (a["kind"], a["addr"], a["val"], a["pc"]) != (b["kind"], b["addr"], b["val"], b["pc"]):
            first = i
            break
    if first is None:
        print("no divergence in first %d entries" % n)
        return
    print("FIRST DIVERGENCE at index %d" % first)
    for j in range(max(0, first - 6), min(n, first + 6)):
        mark = " <== " if j == first else "     "
        a, b = d_ev[j], e_ev[j]
        print("%s[%d] draw  %s %s val=%s pc=%s ra=%s" %
              (mark, j, a["kind"], a["addr"], a["val"], a["pc"], a.get("ra")))
        print("     [%d] empty %s %s val=%s pc=%s ra=%s" %
              (j, b["kind"], b["addr"], b["val"], b["pc"], b.get("ra")))


if __name__ == "__main__":
    main()
