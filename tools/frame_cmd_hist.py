#!/usr/bin/env python3
"""Group recent GTE ring entries by guest frame: if the game draws its 3D view
only every other frame, alternate frames will have (near) zero commands."""
import collections

from input_probe import send


def main():
    port = 4624
    r = send(port, '{"cmd":"gte_ring_dump","count":4000,"newest":1}')
    entries = r["entries"]
    print("entries=%d  total=%s" % (len(entries), r.get("total")))

    per_frame = collections.Counter(e["frame"] for e in entries)
    frames = sorted(per_frame)
    print("frames covered: %d (first=%d last=%d)" % (len(frames), frames[0], frames[-1]))

    counts = [per_frame[f] for f in range(frames[0], frames[-1] + 1)]
    lo = sum(1 for c in counts if c <= 2)
    hi = sum(1 for c in counts if c > 2)
    print("frames with <=2 cmds: %d   with >2 cmds: %d" % (lo, hi))
    print("first 40 per-frame counts:", counts[:40])

    # ra histogram of the busiest call sites
    ra = collections.Counter(e["ra"] for e in entries)
    print("top return addresses:")
    for addr, n in ra.most_common(8):
        print("  %s  %d" % (addr, n))


if __name__ == "__main__":
    main()
