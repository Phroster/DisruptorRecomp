#!/usr/bin/env python3
"""Does the game have vertical look? Sample the GTE projection center (OFY/OFX
from the ring) while holding shoulder/direction buttons."""
import time

from input_probe import BUTTONS, load_state, send


def ofy(port):
    r = send(port, '{"cmd":"gte_ring_dump","count":1,"newest":1}')
    e = r["entries"][-1]
    return int(e["OFX"]), int(e["OFY"]), int(e["H"])


def hold(port, name, secs=0.7):
    word = 0xFFFF & ~BUTTONS[name]
    send(port, '{"cmd":"set_input","buttons":%d}' % word)
    time.sleep(secs)
    vals = [ofy(port) for _ in range(3)]
    send(port, '{"cmd":"clear_input"}')
    time.sleep(0.3)
    return vals


def main():
    port = 4624
    load_state(port, 3)
    print("idle:", ofy(port), flush=True)
    for name in ("l2", "r2", "up", "down", "l1", "r1"):
        print(f"holding {name}:", hold(port, name), flush=True)


if __name__ == "__main__":
    main()
