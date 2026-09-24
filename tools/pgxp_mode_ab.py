#!/usr/bin/env python3
"""A/B the PGXP engine's modes in one saved view (headless is fine).

Usage: python tools/pgxp_mode_ab.py --slot N [--hold left] [--seconds 4]

For each of memory mode / CPU mode it reloads the savestate, holds the pad,
and reports over the window: share of GPU vertices that got a precise position
(dataflow / fallback / native) and the reject counters. "native" vertices sit
on whole pixels next to precise neighbours - those are the seam candidates.
"""
import json
import sys
import time

from ask import ask
from input_probe import BUTTONS

PORT = 4624


def q(**k):
    return ask(PORT, json.dumps(k), timeout=20.0, tries=2)


def window(secs):
    a = q(cmd="geom_correction")["pgxp"]
    time.sleep(secs)
    b = q(cmd="geom_correction")["pgxp"]
    return {k: b[k] - a[k] for k in b if isinstance(b[k], int) and k not in ("enabled", "cpu_mode")}


def main():
    a = sys.argv[1:]
    slot = int(a[a.index("--slot") + 1])
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 4.0
    mask = 0xFFFF
    if "--hold" in a:
        for b in a[a.index("--hold") + 1].split(","):
            mask &= ~BUTTONS[b]
    for cpu_mode in (0, 1):
        q(cmd="clear_input")
        q(cmd="savestate", op="load", slot=slot)
        time.sleep(2.0)
        # Headless starts with the GPU-side lookups off; switch them on live.
        q(cmd="pgxp", cpu_mode=cpu_mode, geometry=1, texture=1)
        q(cmd="set_input", buttons=mask)
        time.sleep(1.0)
        d = window(secs)
        n = max(1, d["lookups"])
        print("cpu_mode=%d lookups %d | dataflow %.2f%% fallback %.2f%% native %.2f%% | "
              "mismatch %d trunc_reject %d tol_reject %d" % (
                  cpu_mode, d["lookups"], 100.0 * d["dataflow_hit"] / n, 100.0 * d["fallback_hit"] / n,
                  100.0 * d["native"] / n, d["value_mismatch"], d["trunc_reject"], d["tolerance_reject"]))
    q(cmd="clear_input")
    q(cmd="pgxp", cpu_mode=0)


if __name__ == "__main__":
    main()
