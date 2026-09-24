#!/usr/bin/env python3
"""Find RAM words that count vblanks: full-RAM snapshot diff timed against the
vblank delivery counter."""
import json
import struct
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4625
RAM_SIZE = 0x200000


def read_ram(port, base, size):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":%d}' % (base, size))
    if not r.get("ok"):
        raise RuntimeError(r)
    return bytes.fromhex(r["hex"])


def vblank(port):
    return send(port, '{"cmd":"vblank_rate"}')["delivered"]


def main():
    chunk = 0x40000
    v0 = vblank(PORT)
    t0 = time.perf_counter()
    snap0 = b"".join(read_ram(PORT, i, chunk) for i in range(0, RAM_SIZE, chunk))
    mid = vblank(PORT)
    snap1 = b"".join(read_ram(PORT, i, chunk) for i in range(0, RAM_SIZE, chunk))
    v1 = vblank(PORT)
    span = time.perf_counter() - t0

    dv = (mid - v0 + v1 - mid) // 2
    print("span=%.2fs vblanks~%d rate=%.1f/s" % (span, dv, dv / span))

    hits = []
    for off in range(0, RAM_SIZE - 4, 4):
        a = struct.unpack_from("<I", snap0, off)[0]
        b = struct.unpack_from("<I", snap1, off)[0]
        d = (b - a) & 0xFFFFFFFF
        if abs(d - dv) <= 2:
            hits.append((0x80000000 + off, a, b, d))
    print("word candidates (delta~%d): %d" % (dv, len(hits)))
    for addr, a, b, d in hits[:25]:
        print("  0x%08X: %d -> %d (+%d)" % (addr, a, b, d))

    hits2 = []
    for off in range(0, RAM_SIZE - 2, 2):
        a = struct.unpack_from("<H", snap0, off)[0]
        b = struct.unpack_from("<H", snap1, off)[0]
        d = (b - a) & 0xFFFF
        if abs(d - dv) <= 2:
            hits2.append((0x80000000 + off, a, b, d))
    print("half candidates: %d (first 15)" % len(hits2))
    for addr, a, b, d in hits2[:15]:
        print("  0x%08X: %d -> %d (+%d)" % (addr, a, b, d))


if __name__ == "__main__":
    main()
