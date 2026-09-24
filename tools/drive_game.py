#!/usr/bin/env python3
"""Keep the game active with synthetic input so hitch rings capture real
gameplay (movement, turning, firing, strafing).

Usage: python tools/drive_game.py [--seconds 120]
"""
import random
import sys
import time

from input_probe import BUTTONS, send

PORT = 4624


def word(*names, base=0xFFFF):
    for n in names:
        base &= ~BUTTONS[n]
    return base


def main():
    seconds = 120
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])
    end = time.time() + seconds
    random.seed(7)
    while time.time() < end:
        combo = random.choice([
            ("up",), ("up", "left"), ("up", "right"),
            ("up", "l2"), ("up", "r2"),
            ("down",), ("left",), ("right",),
        ])
        hold = random.uniform(0.6, 1.4)
        send(PORT, '{"cmd":"set_input","buttons":%d}' % word(*combo))
        # fire periodically while moving
        if random.random() < 0.6:
            send(PORT, '{"cmd":"press","buttons":%d,"frames":3}'
                 % word("cross"))
        time.sleep(hold)
        send(PORT, '{"cmd":"clear_input"}')
        time.sleep(random.uniform(0.1, 0.4))
    send(PORT, '{"cmd":"clear_input"}')
    print("driver done", flush=True)


if __name__ == "__main__":
    main()
