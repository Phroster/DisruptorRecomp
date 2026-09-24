#!/usr/bin/env python3
"""Measure native vs interpreter dispatch rates over a window."""
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4633
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0


def st():
    r = send(PORT, '{"cmd":"overlay_loader_status"}')
    return r["dispatch_native"], r["dispatch_interp_fallback"]


n0, i0 = st()
time.sleep(SECS)
n1, i1 = st()
dn, di = n1 - n0, i1 - i0
tot = max(1, dn + di)
print("over %.0fs: native +%d (%.2f%%), interp +%d (%.2f%%)"
      % (SECS, dn, 100.0 * dn / tot, di, 100.0 * di / tot))
