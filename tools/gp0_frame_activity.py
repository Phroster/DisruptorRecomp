#!/usr/bin/env python3
"""Per-frame GP0 draw activity: dumps recent guest frames from the GP0 ring and
reports command counts per frame (detect 30 Hz 3D rendering)."""
import collections
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4625
NFRAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 8


def main():
    st = send(PORT, '{"cmd":"gpu_ring_stats"}')
    print("ring:", {k: st[k] for k in ("total", "capacity", "max_words",
                                       "oldest_frame", "newest_frame")})
    newest = st["newest_frame"]
    oldest = st["oldest_frame"]

    for f in range(newest - NFRAMES + 1, newest + 1):
        if f < oldest:
            print("frame %d: evicted" % f)
            continue
        r = send(PORT, '{"cmd":"gpu_frame_dump","frame":%d,"count":65536}' % f)
        ev = r.get("entries", [])
        ops = collections.Counter()
        draws = 0
        for e in ev:
            op = e.get("op") or "0x00"
            ops[op] += 1
            v = int(op, 16)
            if 0x20 <= v <= 0x7F:
                draws += 1
        top = ops.most_common(8)
        print("frame %d: commands=%d draws=%d top=%s" %
              (f, len(ev), draws, top))


if __name__ == "__main__":
    main()
