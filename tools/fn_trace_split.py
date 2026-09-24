#!/usr/bin/env python3
"""Aggregate fn_entry tail over a window, split functions by frame parity
(draw frames vs empty frames), using the GP0 ring to identify drawn frames."""
import collections
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4625
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0


def main():
    # which recent frames drew?
    st = send(PORT, '{"cmd":"gpu_ring_stats"}')
    newest_frame = st["newest_frame"]
    drawn = set()
    for f in range(newest_frame - 6, newest_frame + 1):
        r = send(PORT, '{"cmd":"gpu_frame_dump","frame":%d,"count":8}' % f)
        if r.get("count", 0) > 0:
            drawn.add(f)
    print("drawn frames sample:", sorted(drawn))

    per_frame = collections.defaultdict(collections.Counter)
    seen = set()
    print(send(PORT, '{"cmd":"fn_filter","lo":"0x0","hi":"0x200000"}'))
    print(send(PORT, '{"cmd":"fn_clear"}'))
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < DUR:
        d = send(PORT, '{"cmd":"fn_entry_tail","count":256}')
        for e in d.get("entries", []):
            key = (e["seq"],)
            if key in seen:
                continue
            seen.add(key)
            per_frame[e["frame"]][e["func"]] += 1
    print(send(PORT, '{"cmd":"fn_disable"}'))

    def parity(f):
        return "draw" if f in drawn or (f % 2) in (f % 2 for f in drawn) else "empty"

    # classify frames by odd/even of a drawn frame
    if drawn:
        draw_par = min(drawn) % 2
    else:
        draw_par = 0
    both = collections.defaultdict(lambda: [0, 0])
    for f, funcs in per_frame.items():
        idx = 0 if (f % 2) == draw_par else 1
        for fn, n in funcs.items():
            both[fn][idx] += n
    print("frames captured: %d (draw-parity %d)" % (len(per_frame), draw_par))
    only_draw = [(fn, v[0]) for fn, v in both.items() if v[0] > 0 and v[1] == 0]
    only_empty = [(fn, v[1]) for fn, v in both.items() if v[1] > 0 and v[0] == 0]
    both_cnt = [(fn, v) for fn, v in both.items() if v[0] > 0 and v[1] > 0]
    print("funcs only on draw frames (%d):" % len(only_draw))
    for fn, n in sorted(only_draw, key=lambda x: -x[1])[:20]:
        print("   %s x%d" % (fn, n))
    print("funcs only on empty frames (%d):" % len(only_empty))
    for fn, n in sorted(only_empty, key=lambda x: -x[1])[:12]:
        print("   %s x%d" % (fn, n))
    print("funcs on both (%d), top:" % len(both_cnt))
    for fn, v in sorted(both_cnt, key=lambda x: -(x[1][0] + x[1][1]))[:12]:
        print("   %s draw=%d empty=%d" % (fn, v[0], v[1]))


if __name__ == "__main__":
    main()
