#!/usr/bin/env python3
"""Locate the player yaw variable by value search.

Reads the newest GTE RT matrix (camera rotation), computes the Y angle in Q12,
and scans guest RAM for 16-bit little-endian words matching that angle (and its
negation/offset variants). Repeats at a second camera heading: only an address
that tracks the heading both times is a yaw candidate.

Usage: python tools/find_yaw3.py [--port 4624] [--slot 3]
"""
import argparse
import json
import math
import struct
import sys
import time

from input_probe import BUTTONS, load_state, read_ram, send

TOL = 8


def newest_rt(port):
    r = send(port, '{"cmd":"gte_ring_dump","count":1,"newest":1}')
    e = r["entries"][-1]
    return [int(x) for x in e["RT"]], int(e["frame"])


def angle_candidates(rt):
    """Y-rotation angle from a Q12 3x3, plus variants the game may store."""
    cos = rt[0] / 4096.0
    sin = rt[2] / 4096.0
    yaw = math.degrees(math.atan2(sin, cos)) % 360.0
    vals = []
    q12 = int(round(yaw / 360.0 * 4096)) & 0xFFF
    vals.append(("yaw_q12", q12))
    vals.append(("neg_q12", (-q12) & 0xFFF))
    q12_16 = int(round(yaw / 360.0 * 65536)) & 0xFFFF
    vals.append(("yaw_16", q12_16))
    vals.append(("neg_16", (-q12_16) & 0xFFFF))
    deg16 = int(round(yaw * 182)) & 0xFFFF     # 65536/360
    vals.append(("deg16", deg16))
    return yaw, vals


def scan(ram, want, tol=TOL):
    hits = []
    for i in range(0, len(ram) - 1, 2):
        v = ram[i] | (ram[i + 1] << 8)
        for name, target in want:
            d = abs(v - target)
            d = min(d, 65536 - d)
            if d <= tol:
                hits.append((i, v, name))
                break
    return hits


def sample(port):
    """Read RAM, then immediately the newest camera matrix."""
    ram = read_ram(port)
    rt, frame = newest_rt(port)
    yaw, _ = angle_candidates(rt)
    return ram, yaw


def offsets_16(ram, yaw_deg):
    """Per-addressed 16-bit word angle minus the ring yaw, in degrees."""
    out = {}
    for i in range(0, len(ram) - 1, 2):
        v = ram[i] | (ram[i + 1] << 8)
        out[i] = (v / 4096.0 * 360.0 - yaw_deg) % 360.0
    return out


def offsets_32(ram, yaw_deg):
    out = {}
    for i in range(0, len(ram) - 3, 2):
        v = struct.unpack_from("<I", ram, i)[0]
        if v == 0:
            continue
        q16 = v & 0xFFFF
        # Q16 over the full turn and Q12 in the low half both appear in PsyQ code.
        for scale, mask in ((65536.0, 0xFFFF), (4096.0, 0x0FFF)):
            a = (v % scale) / scale * 360.0
            d = (a - yaw_deg) % 360.0
            out[(i, "q16" if scale == 65536.0 else "q12w")] = d
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    args = ap.parse_args()

    load_state(args.port, args.slot)
    send(args.port, '{"cmd":"set_input","buttons":%d}' % (0xFFFF & ~BUTTONS["right"]))
    time.sleep(0.4)
    send(args.port, '{"cmd":"clear_input"}')
    time.sleep(0.3)
    ram1, yaw1 = sample(args.port)
    off1 = offsets_16(ram1, yaw1)
    off1b = offsets_16(bytes(ram1), -yaw1)
    print(f"heading1 ring yaw={yaw1:.2f}deg", flush=True)

    send(args.port, '{"cmd":"set_input","buttons":%d}' % (0xFFFF & ~BUTTONS["left"]))
    time.sleep(0.25)
    send(args.port, '{"cmd":"clear_input"}')
    time.sleep(0.3)
    ram2, yaw2 = sample(args.port)
    off2 = offsets_16(ram2, yaw2)
    off2b = offsets_16(bytes(ram2), -yaw2)
    print(f"heading2 ring yaw={yaw2:.2f}deg", flush=True)

    cands = []
    for i in off1:
        d1, d2 = off1[i], off2.get(i)
        if d2 is None:
            continue
        e1 = min(abs(d1 - d2), 360 - abs(d1 - d2))
        e2 = min(abs(d1 - d2), 360 - abs(d1 - d2))
        # also try the mirrored convention (angle stored negated)
        e1b = min(abs(off1b[i] - off2b.get(i, -1)), 360 - abs(off1b[i] - off2b.get(i, -1)))
        if e1 <= 2.0 or e1b <= 2.0:
            v1 = ram1[i] | (ram1[i + 1] << 8)
            v2 = ram2[i] | (ram2[i + 1] << 8)
            cands.append((i, v1, v2, d1, d2, min(e1, e1b)))
    print(f"constant-offset 16-bit candidates: {len(cands)}")
    for i, v1, v2, d1, d2, e in cands[:40]:
        print(f"  0x{i:06X}  h1={v1:#06x}(off {d1:6.1f})  h2={v2:#06x}(off {d2:6.1f})  err={e:.2f}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
