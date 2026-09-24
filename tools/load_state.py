#!/usr/bin/env python3
"""Request a savestate load over the debug port and WAIT until it has applied.

Usage: python tools/load_state.py --slot N [--timeout 60]
Exit code 0 when the runtime reports the load done, 1 on failure/timeout.
(The request is only staged by the command; the game thread applies it later,
which can take seconds while the game idles in a menu.)
"""
import json
import sys
import time

from ask import ask

PORT = 4624


def q(**k):
    return ask(PORT, json.dumps(k), timeout=20.0, tries=2)


def main():
    a = sys.argv[1:]
    slot = int(a[a.index("--slot") + 1])
    timeout = float(a[a.index("--timeout") + 1]) if "--timeout" in a else 60.0
    g0 = q(cmd="savestate_status").get("generation", 0)
    q(cmd="clear_input")
    q(cmd="savestate", op="load", slot=slot)
    end = time.time() + timeout
    while time.time() < end:
        s = q(cmd="savestate_status")
        if s.get("generation", 0) != g0 and not s.get("pending"):
            ok = bool(s.get("last_ok"))
            print("load slot %d: %s" % (slot, "applied" if ok else "FAILED"))
            time.sleep(1.5)
            sys.exit(0 if ok else 1)
        time.sleep(0.25)
    print("load slot %d: timed out" % slot)
    sys.exit(1)


if __name__ == "__main__":
    main()
