#!/usr/bin/env python3
"""Headless per-button function probe.

For each PSX button: load savestate slot 3, snapshot RAM, take a drift window
(no input), then the test window (button held via set_input), diff the two
windows, and report the bytes that changed under input but not under drift.
That fingerprint classifies what the button actually does in the running game
(fire -> ammo/psi counters; jump -> vertical coordinate; weapon -> index +
ammo; strafe/turn -> position vs facing; use -> little or nothing).

Usage: python tools/input_probe.py [--port 4624] [--slot 3] [--only cross,...]
"""
import argparse
import json
import socket
import sys
import time

RAM_BASE = 0x00000000
RAM_SIZE = 0x200000          # 2 MiB

# Active-low pad words (bit cleared = pressed).
BUTTONS = {
    "select":   (1 << 0),
    "start":    (1 << 3),
    "up":       (1 << 4),
    "right":    (1 << 5),
    "down":     (1 << 6),
    "left":     (1 << 7),
    "l2":       (1 << 8),
    "r2":       (1 << 9),
    "l1":       (1 << 10),
    "r1":       (1 << 11),
    "triangle": (1 << 12),
    "circle":   (1 << 13),
    "cross":    (1 << 14),
    "square":   (1 << 15),
}


def send(port, payload, timeout=30.0):
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall((payload + "\n").encode())
        s.settimeout(timeout)
        buf = b""
        while True:
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            buf += chunk
            if buf.rstrip().endswith(b"}"):
                break
    for line in buf.decode(errors="replace").splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError("no JSON in response: " + buf[:120].decode(errors="replace"))


def read_ram(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":%d}' % (RAM_BASE, RAM_SIZE))
    if not r.get("ok"):
        raise RuntimeError(r)
    return bytes.fromhex(r["hex"])


def read_scratch(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x1F800000","len":1024}')
    if not r.get("ok"):
        raise RuntimeError(r)
    return bytes.fromhex(r["hex"])


def probe_scratch(port, name, slot, verbose):
    word = 0xFFFF & ~BUTTONS[name]
    load_state(port, slot)
    snap0 = read_scratch(port)
    time.sleep(0.6)
    snap1 = read_scratch(port)
    drift = {i for i, _, _ in diff(snap0, snap1)}
    send(port, '{"cmd":"press","buttons":%d,"frames":6}' % word)
    time.sleep(0.6)
    snap2 = read_scratch(port)
    novel = [(i, a, b) for i, a, b in diff(snap1, snap2) if i not in drift]
    print(f"== {name} (scratch): drift={len(drift)} novel={len(novel)}")
    for i, a, b in novel:
        if verbose or abs(b - a) >= 2 or i in (0x176, 0x186):
            print(f"   * 0x1F800{i:03X}  {a:#04x} -> {b:#04x}  ({b - a:+d})")
    sys.stdout.flush()


def load_state(port, slot):
    r = send(port, '{"cmd":"savestate","op":"load","slot":%d}' % slot)
    if not r.get("ok"):
        raise RuntimeError(r)
    time.sleep(2.5)


def press_hold(port, word):
    send(port, '{"cmd":"set_input","buttons":%d}' % word)


def release(port):
    send(port, '{"cmd":"clear_input"}')


def diff(a, b):
    out = []
    for i in range(len(a)):
        if a[i] != b[i]:
            out.append((i, a[i], b[i]))
    return out


def probe(port, name, slot, verbose):
    word = 0xFFFF & ~BUTTONS[name]
    load_state(port, slot)
    # Drift window: same timing without input.
    snap0 = read_ram(port)
    time.sleep(0.6)
    snap1 = read_ram(port)
    drift = {i for i, _, _ in diff(snap0, snap1)}
    # Test window: one short press.
    send(port, '{"cmd":"press","buttons":%d,"frames":6}' % word)
    time.sleep(0.6)
    snap2 = read_ram(port)
    test = diff(snap1, snap2)
    novel = [(i, a, b) for i, a, b in test if i not in drift]
    small = [(i, a, b) for i, a, b in novel if 0 < abs(b - a) <= 64]
    print(f"== {name}: word=0x{word:04X} drift={len(drift)} test={len(test)} "
          f"novel={len(novel)} small_delta={len(small)}")
    for i, a, b in small[:32]:
        print(f"   * 0x{i & 0x1FFFFF:06X}  {a:#04x} -> {b:#04x}  ({b - a:+d})")
    if verbose:
        for i, a, b in novel[:40]:
            print(f"   . 0x{i & 0x1FFFFF:06X}  {a:#04x} -> {b:#04x}  ({b - a:+d})")
    sys.stdout.flush()
    return novel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--slot", type=int, default=3)
    ap.add_argument("--only", default="")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--scratch", action="store_true")
    args = ap.parse_args()
    names = args.only.split(",") if args.only else list(BUTTONS)
    for name in names:
        if name not in BUTTONS:
            print("unknown:", name)
            continue
        try:
            if args.scratch:
                probe_scratch(args.port, name, args.slot, args.verbose)
            else:
                probe(args.port, name, args.slot, args.verbose)
        except Exception as exc:
            print("ERR", name, exc)


if __name__ == "__main__":
    main()
