#!/usr/bin/env python3
"""Hold pad buttons and save N presented frames while the view moves.

Usage: python tools/turn_shots.py --prefix logs/turn_a [--hold left] [--n 6] [--gap 0.4]
"""
import json
import os
import subprocess
import sys
import time

from ask import ask
from input_probe import BUTTONS

PORT = 4624
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    a = sys.argv[1:]
    prefix = a[a.index("--prefix") + 1]
    n = int(a[a.index("--n") + 1]) if "--n" in a else 6
    gap = float(a[a.index("--gap") + 1]) if "--gap" in a else 0.4
    settle = float(a[a.index("--settle") + 1]) if "--settle" in a else 2.5
    mask = 0xFFFF
    for b in (a[a.index("--hold") + 1] if "--hold" in a else "left").split(","):
        mask &= ~BUTTONS[b]
    # The composed-frame capture lags a few seconds behind a savestate load.
    time.sleep(settle)
    ask(PORT, json.dumps({"cmd": "set_input", "buttons": mask}), timeout=10.0, tries=2)
    time.sleep(0.6)
    for i in range(n):
        subprocess.run([sys.executable, os.path.join(HERE, "shot.py"), "--wait", "0", "--out",
                        "%s_%d.png" % (prefix, i)], stdout=subprocess.DEVNULL)
        time.sleep(gap)
    ask(PORT, json.dumps({"cmd": "clear_input"}), timeout=10.0, tries=2)


if __name__ == "__main__":
    main()
