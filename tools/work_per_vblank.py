#!/usr/bin/env python3
"""How much does the engine draw per guest VBlank? (diagnostics build)

Usage: python tools/work_per_vblank.py [--slot N] [--seconds 6]
Prints GP0 draw commands, display flips and terrain-render calls per
delivered VBlank. If the engine runs more than one update+render pass per
VBlank (it free-runs once its frame-sync waits are patched out and the guest
CPU is overclocked), draws per VBlank rise with the overclock while the
picture rate stays at one flip per VBlank.
"""
import json
import sys
import time

from ask import ask

PORT = 4624


def q(c, **k):
    d = {"cmd": c}
    d.update(k)
    return ask(PORT, json.dumps(d), timeout=20.0, tries=2)


def snap():
    g = q("gpu_state")
    v = q("vblank_rate")
    return g["gp0_draw"], g["gp0_fill"], v["delivered"]


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 6.0
    if "--slot" in a:
        q("savestate", op="load", slot=int(a[a.index("--slot") + 1]))
        time.sleep(4)
    d0, f0, v0 = snap()
    time.sleep(secs)
    d1, f1, v1 = snap()
    vb = max(1, v1 - v0)
    print("VBlanks %d | draw cmds/VBlank %.1f | screen clears (= render passes)/VBlank %.2f"
          % (vb, (d1 - d0) / vb, (f1 - f0) / vb))


if __name__ == "__main__":
    main()
