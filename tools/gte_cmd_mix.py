#!/usr/bin/env python3
"""Compare GTE command mix on a drawn frame vs an empty frame."""
import collections
import sys

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4625

CMD = {
    0x01: "RTPS", 0x02: "NCLIP", 0x06: "NCDS", 0x0C: "OP", 0x10: "DPCS",
    0x11: "INTPL", 0x12: "MVMVA", 0x13: "NCDT", 0x16: "NCDS?", 0x1B: "NCCS",
    0x1C: "CC", 0x1E: "NCS", 0x20: "NCT", 0x28: "SQR", 0x29: "DCPL",
    0x2A: "DPCT", 0x2D: "AVSZ3", 0x2E: "AVSZ4", 0x30: "RTPT", 0x3D: "GPF",
    0x3E: "GPL", 0x3F: "NCCT",
}


def dump(port, frame):
    r = send(port, '{"cmd":"gte_ring_dump","frame":%d,"count":65536}' % frame)
    ev = r.get("entries", [])
    c = collections.Counter()
    ra = collections.Counter()
    for e in ev:
        cmd = int(e["cmd"], 16) & 0x3F
        c[CMD.get(cmd, "0x%02X" % cmd)] += 1
        ra[e["ra"]] += 1
    print("frame %d: entries=%d cmd mix=%s" % (frame, len(ev), c.most_common(8)))
    print("  ra:", ra.most_common(6))


def main():
    st = send(PORT, '{"cmd":"gpu_ring_stats"}')
    f = st["newest_frame"]
    for fr in (f, f - 1, f - 2, f - 3):
        dump(PORT, fr)


if __name__ == "__main__":
    main()
