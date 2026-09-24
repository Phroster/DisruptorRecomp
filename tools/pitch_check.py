#!/usr/bin/env python3
"""Verify pitch: injected mouse Y must add pitch terms to the camera matrix."""
import time

from input_probe import load_state, send


def rt(port):
    r = send(port, '{"cmd":"gte_ring_dump","count":1,"newest":1}')
    return [int(x) for x in r["entries"][-1]["RT"]]


def yaw(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x80077624","len":1}')
    return int(r["hex"], 16)


def main():
    port = 4624
    load_state(port, 3)
    print("baseline yaw:", yaw(port), "RT:", rt(port), flush=True)

    for dy in (200, 200, -400):
        send(port, '{"cmd":"host_mouse","dy":%d}' % dy)
        time.sleep(0.25)
        print(f"after dy={dy:4d}: yaw={yaw(port)} RT={rt(port)}", flush=True)

    # Yaw still works alongside pitch.
    send(port, '{"cmd":"host_mouse","dx":150}')
    time.sleep(0.25)
    print("after dx=150 (+pitch held): RT=", rt(port), flush=True)


if __name__ == "__main__":
    main()
