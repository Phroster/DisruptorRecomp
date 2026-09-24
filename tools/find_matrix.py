#!/usr/bin/env python3
"""Find where the camera rotation matrix lives in guest RAM.

Reads the newest GTE RT (the matrix the game loaded), then scans RAM and the
scratchpad for the same 9 Q12 elements, trying halfword rows, word rows and
transposes. The hit address is the matrix the camera build writes; its writer
PC leads to the yaw source.

Usage: python tools/find_matrix.py [--port 4624] [--slot 3]
"""
import argparse
import struct
import sys
import time

from input_probe import load_state, send


def newest_rt(port):
    r = send(port, '{"cmd":"gte_ring_dump","count":1,"newest":1}')
    e = r["entries"][-1]
    return [int(x) for x in e["RT"]]


def read(port, addr, length):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":%d}' % (addr, length))
    return bytes.fromhex(r["hex"])


def pack16(vals):
    return struct.pack("<9h", *[max(-32768, min(32767, v)) for v in vals])


def pack32(vals):
    return struct.pack("<9i", *vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    args = ap.parse_args()
    load_state(args.port, args.slot)

    rt = newest_rt(args.port)
    print("ring RT:", rt)
    variants = {
        "rows16": pack16(rt),
        "rows32": pack32(rt),
    }
    tr = [rt[0], rt[3], rt[6], rt[1], rt[4], rt[7], rt[2], rt[5], rt[8]]
    variants["tr16"] = pack16(tr)
    variants["tr32"] = pack32(tr)
    # Negated forms (camera vs world convention).
    variants["neg16"] = pack16([-v for v in rt])

    regions = [("ram", 0x0, 0x200000), ("scratch", 0x1F800000, 0x400)]
    for rname, base, length in regions:
        blob = read(args.port, base, length)
        for vname, pat in variants.items():
            start = 0
            hits = []
            while True:
                i = blob.find(pat, start)
                if i < 0:
                    break
                hits.append(base + i)
                start = i + 1
            if hits:
                print(f"{rname} {vname}: {len(hits)} hits "
                      f"{[hex(h) for h in hits[:8]]}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
