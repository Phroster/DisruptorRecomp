#!/usr/bin/env python3
"""Who submits the GP0 draws, and does the skipped frame still transform?"""
import collections
import sys

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4625


def main():
    st = send(PORT, '{"cmd":"gpu_ring_stats"}')
    f = st["newest_frame"]
    print("newest frame:", f)

    for fr in (f, f - 1):
        d = send(PORT, '{"cmd":"gpu_frame_dump","frame":%d,"count":65536}' % fr)
        ev = d.get("entries", [])
        pcs = collections.Counter(e["pc"] for e in ev)
        ras = collections.Counter(e["ra"] for e in ev)
        funcs = collections.Counter(e["func"] for e in ev)
        print("frame %d: commands=%d" % (fr, len(ev)))
        if ev:
            print("  pc:", pcs.most_common(5))
            print("  ra:", ras.most_common(5))
            print("  func:", funcs.most_common(5))

        g = send(PORT, '{"cmd":"gte_ring_dump","frame":%d,"count":65536}' % fr)
        ge = g.get("entries", [])
        print("  gte entries: %s" % len(ge))
        if ge:
            gra = collections.Counter(e["ra"] for e in ge)
            print("  gte ra:", gra.most_common(5))


if __name__ == "__main__":
    main()
