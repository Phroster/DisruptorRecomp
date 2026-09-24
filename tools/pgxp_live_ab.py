#!/usr/bin/env python3
"""Live A/B of the PGXP settings in whatever scene the running GL build shows.

Usage: python tools/pgxp_live_ab.py [--seconds 3] [--hold left] [--shots logs/pgxp_ab]

Switches through: geometry off / memory mode / CPU mode / memory mode + 0.5 px
clamp, without reloading anything (so every arm sees the same scene), and
prints per arm the share of GPU vertices that got a precise position. "native"
vertices stay on whole pixels next to precise neighbours: seam candidates.
With --shots it saves the presented frame of every arm.
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


def q(**k):
    return ask(PORT, json.dumps(k), timeout=20.0, tries=2)


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 3.0
    shots = a[a.index("--shots") + 1] if "--shots" in a else None
    mask = 0xFFFF
    if "--hold" in a:
        for b in a[a.index("--hold") + 1].split(","):
            mask &= ~BUTTONS[b]
    arms = [("geometry_off", dict(geometry=0, texture=1, cpu_mode=0, tolerance=-1.0)),
            ("memory_mode", dict(geometry=1, texture=1, cpu_mode=0, tolerance=-1.0)),
            ("cpu_mode", dict(geometry=1, texture=1, cpu_mode=1, tolerance=-1.0)),
            ("memory_clamp05", dict(geometry=1, texture=1, cpu_mode=0, tolerance=0.5))]
    for name, cfg in arms:
        q(cmd="pgxp", **cfg)
        q(cmd="set_input", buttons=mask)
        time.sleep(1.0)
        s0 = q(cmd="geom_correction")["pgxp"]
        time.sleep(secs)
        s1 = q(cmd="geom_correction")["pgxp"]
        q(cmd="clear_input")
        d = {k: s1[k] - s0[k] for k in s1 if isinstance(s1[k], int) and k not in ("enabled", "cpu_mode")}
        n = max(1, d["lookups"])
        print("%-15s lookups %7d | dataflow %5.1f%% fallback %4.1f%% native %5.1f%% | mismatch %d trunc %d tol %d" % (
            name, d["lookups"], 100.0 * d["dataflow_hit"] / n, 100.0 * d["fallback_hit"] / n,
            100.0 * d["native"] / n, d["value_mismatch"], d["trunc_reject"], d["tolerance_reject"]))
        if shots:
            time.sleep(0.5)
            subprocess.run([sys.executable, os.path.join(HERE, "shot.py"), "--out", "%s_%s.png" % (shots, name)],
                           stdout=subprocess.DEVNULL)
    q(cmd="pgxp", geometry=1, texture=1, cpu_mode=0, tolerance=-1.0)


if __name__ == "__main__":
    main()
