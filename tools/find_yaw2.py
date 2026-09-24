#!/usr/bin/env python3
"""Find the yaw variable via write-trace differential.

Arms wtrace over all RAM, holds a turn button for a second, and histograms the
written addresses. The yaw counter is written once per guest frame while
turning only, so differencing the turn histogram against an idle histogram
isolates it.

Usage: python tools/find_yaw2.py [--port 4624] [--slot 3] [--button right]
"""
import argparse
import json
import socket
import sys
import time
from collections import Counter

from input_probe import send


def dump(port, count=2048):
    r = send(port, '{"cmd":"wtrace_dump","newest":1,"count":%d}' % count)
    return r.get("entries", [])


def window(port, word, label, count):
    send(port, '{"cmd":"wtrace_reset"}')
    if word is not None:
        send(port, '{"cmd":"set_input","buttons":%d}' % word)
    time.sleep(1.0)
    entries = []
    for _ in range(4):
        entries.extend(dump(port, count))
        time.sleep(0.05)
    if word is not None:
        send(port, '{"cmd":"clear_input"}')
    hist = Counter()
    for e in entries:
        hist[int(e["addr"], 16)] += 1
    print(f"  {label}: {len(entries)} writes, {len(hist)} distinct addrs", flush=True)
    return hist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    ap.add_argument("--button", default="right")
    args = ap.parse_args()
    from input_probe import BUTTONS, load_state
    word = 0xFFFF & ~BUTTONS[args.button]

    send(args.port, '{"cmd":"wtrace_arm","lo":"0x0","hi":"0x200000"}')
    load_state(args.port, args.slot)
    idle = window(args.port, None, "idle", 2048)
    load_state(args.port, args.slot)
    turn = window(args.port, word, f"turn {args.button}", 2048)

    novel = []
    for addr, c in turn.items():
        if idle.get(addr, 0) == 0:
            novel.append((addr, c))
    novel.sort(key=lambda t: -t[1])
    print(f"addresses written while turning but never idle: {len(novel)}")
    for addr, c in novel[:40]:
        print(f"  0x{addr:06X}  writes={c}")
    # Also: addresses written often in both, but far more often when turning.
    ratio = []
    for addr, c in turn.items():
        i = idle.get(addr, 0)
        if i and c > 3 * i and c >= 20:
            ratio.append((addr, c, i))
    ratio.sort(key=lambda t: -(t[1] / t[2]))
    print(f"turn-amplified addresses: {len(ratio)}")
    for addr, c, i in ratio[:20]:
        print(f"  0x{addr:06X}  turn={c} idle={i}")


if __name__ == "__main__":
    main()
