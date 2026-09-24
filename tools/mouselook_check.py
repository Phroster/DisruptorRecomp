#!/usr/bin/env python3
"""Verify true mouselook: injected mouse deltas move the yaw byte 1:1, opposite
signs reverse, and idle leaves it untouched."""
import time

from input_probe import load_state, send

YAW = 0x80077624


def yaw(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % YAW)
    return int(r["hex"], 16)


def rt(port):
    r = send(port, '{"cmd":"gte_ring_dump","count":1,"newest":1}')
    return [int(x) for x in r["entries"][-1]["RT"]]


def main():
    port = 4624
    load_state(port, 3)
    base = yaw(port)
    print("baseline yaw:", base, "RT:", rt(port)[:3], flush=True)

    time.sleep(1.0)
    print("after 1s idle:", yaw(port), flush=True)

    for dx in (100, -60, 40):
        before = yaw(port)
        send(port, '{"cmd":"host_mouse","dx":%d}' % dx)
        time.sleep(0.2)
        after = yaw(port)
        exp = dx * 0.22 / (360.0 / 256.0)
        got = (after - before) % 256
        signed = got - 256 if got > 127 else got
        print(f"dx={dx:5d}: yaw {before} -> {after} (delta {signed:+d}, "
              f"expected {exp:+.1f})  RT={rt(port)[:3]}", flush=True)
        time.sleep(0.2)


if __name__ == "__main__":
    main()
