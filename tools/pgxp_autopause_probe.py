#!/usr/bin/env python3
"""Helper for tools/pgxp_autopause_check.ps1.

  intro  - uncapped guest VBlank rate over 14 s, then the PGXP engine state
  state  - the PGXP engine state only ("active" 0 = paused)
"""
import json
import sys
import time

from ask import ask

PORT = 4624


def q(**k):
    return ask(PORT, json.dumps(k), timeout=20.0, tries=2)


def main():
    if sys.argv[1] == "intro":
        v0 = q(cmd="vblank_rate")["delivered"]
        t0 = time.perf_counter()
        time.sleep(14)
        v1 = q(cmd="vblank_rate")["delivered"]
        print("intro guest Hz uncapped: %.1f" % ((v1 - v0) / (time.perf_counter() - t0)))
    d = q(cmd="pgxp")
    print("pgxp enabled=%s active=%s suppress=%s" % (d.get("enabled"), d.get("active"), d.get("suppress")))


if __name__ == "__main__":
    main()
