#!/usr/bin/env python3
"""Find the yaw write by per-frame write-trace.

Arms wtrace over all RAM, turns for a second, then dumps the writes of the
last few frames in address chunks (the response caps at 2048 entries, so the
address space is swept). Addresses written in every turn frame with a changing
value, and not written while idle, are candidates for the yaw counter.

Usage: python tools/find_yaw4.py [--port 4624] [--slot 3]
"""
import argparse
import sys
import time
from collections import defaultdict

from input_probe import BUTTONS, load_state, send

CHUNK = 0x20000          # 128 KiB
CHUNKS = 0x200000 // CHUNK


def writes_for_window(port, f_lo, f_hi):
    """addr -> list of (frame, old, new, pc) across the whole RAM, chunk-swept."""
    out = []
    for c in range(CHUNKS):
        lo = c * CHUNK
        hi = lo + CHUNK
        r = send(port, '{"cmd":"wtrace_dump","addr_lo":"0x%X","addr_hi":"0x%X",'
                       '"frame_lo":%d,"frame_hi":%d,"count":2048}'
                 % (lo, hi, f_lo, f_hi))
        out.extend(r.get("entries", []))
    return out


def frame_now(port):
    r = send(port, '{"cmd":"gpu_state"}')
    return int(r["ws"]["cur_frame"])


def collect(port, label, turn):
    if turn:
        send(port, '{"cmd":"set_input","buttons":%d}' % (0xFFFF & ~BUTTONS["right"]))
    time.sleep(1.0)
    f = frame_now(port)
    per_frame = {}
    for df in range(4):
        per_frame[df] = writes_for_window(port, f - df, f - df)
    if turn:
        send(port, '{"cmd":"clear_input"}')
    print(f"  {label}: frame {f}, writes/frame="
          f"{[len(v) for v in per_frame.values()]}", flush=True)
    return per_frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    args = ap.parse_args()

    send(args.port, '{"cmd":"wtrace_arm","lo":"0x0","hi":"0x200000"}')
    load_state(args.port, args.slot)
    idle = collect(args.port, "idle", False)
    idle_addrs = set()
    for v in idle.values():
        for e in v:
            idle_addrs.add(int(e["addr"], 16))
    load_state(args.port, args.slot)
    turn = collect(args.port, "turn", True)

    # addr -> {frame_off: new_value}
    seen = defaultdict(dict)
    meta = {}
    for df, entries in turn.items():
        for e in entries:
            a = int(e["addr"], 16)
            seen[a][df] = int(e["new"], 16)
            meta[a] = (e["pc"], e["old"], e["new"])
    cands = []
    for a, byf in seen.items():
        if a in idle_addrs:
            continue
        if len(byf) < 3:
            continue
        vals = [byf[k] for k in sorted(byf)]
        if len(set(vals)) < 2:
            continue
        cands.append((a, vals, meta[a][0]))
    cands.sort(key=lambda t: (len(t[1]), t[0]))
    print(f"candidates (written most turn frames, changing, not idle): {len(cands)}")
    for a, vals, pc in cands[:40]:
        print(f"  0x{a:06X} pc={pc} vals={vals}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
