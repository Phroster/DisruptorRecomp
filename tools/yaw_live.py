#!/usr/bin/env python3
"""Live check: the camera yaw byte at 0x80077624 and the GTE RT matrix while
a turn button is held."""
import time

from input_probe import BUTTONS, load_state, send

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
    print("idle yaw:", yaw(port), "RT:", rt(port)[:3], flush=True)
    send(port, '{"cmd":"set_input","buttons":%d}' % (0xFFFF & ~BUTTONS["right"]))
    for _ in range(6):
        time.sleep(0.15)
        print("turning yaw:", yaw(port), "RT:", rt(port)[:3], flush=True)
    send(port, '{"cmd":"clear_input"}')


if __name__ == "__main__":
    main()
