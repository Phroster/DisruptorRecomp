#!/usr/bin/env python3
"""Sample dirty_ram_stats counters twice and print the deltas.

Usage: python tools/stats_delta.py <port> <secs>
"""
import json
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4634
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0


def stats():
    with socket.create_connection(("127.0.0.1", PORT), timeout=30) as s:
        s.sendall(b'{"cmd":"dirty_ram_stats"}\n')
        s.settimeout(30)
        buf = b""
        while not buf.endswith(b"\n"):
            c = s.recv(1 << 20)
            if not c:
                break
            buf += c
    return json.loads(buf.decode(errors="replace"))


a = stats()
time.sleep(SECS)
b = stats()
for k in ("blocks_run", "insns_run", "aborts", "guard_yields",
          "native_handoffs", "text_native_blocked", "text_diverged_pages",
          "text_exact_mismatches"):
    va, vb = a.get(k, 0), b.get(k, 0)
    print("%-22s +%d  (%.0f/s)" % (k, vb - va, (vb - va) / SECS))

pa = {e["pc"]: e for e in a.get("per_pc", [])}
pb = {e["pc"]: e for e in b.get("per_pc", [])}
hot = sorted(set(pa) | set(pb),
             key=lambda pc: -(pb.get(pc, {}).get("hits", 0)
                              - pa.get(pc, {}).get("hits", 0)))[:12]
print("top interpreted PCs this window:")
for pc in hot:
    d = pb.get(pc, {}).get("hits", 0) - pa.get(pc, {}).get("hits", 0)
    if d > 0:
        print("  %s  hits+%d" % (pc, d))
