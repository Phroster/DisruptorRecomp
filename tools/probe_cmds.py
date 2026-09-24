#!/usr/bin/env python3
"""Probe which diagnostic command names the runtime accepts.

Sends each candidate as {"cmd":NAME} and prints ok/unknown. Then, with
--dump NAME [json-args], prints the raw reply of one command.
"""
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4634

NAMES = [
    "overlay_loader_status", "overlay_candidates", "overlay_native_ring",
    "overlay_interp_ring", "interp_ring", "overlay_capture_dump",
    "overlay_rescan", "overlay_shadow_dump", "overlay_shadow_detail",
    "overlay_diff_on", "overlay_diff_off", "overlay_irq_dump",
    "dirty_n", "dirty_ram_n", "n_ring", "overlay_ring",
    "overlay_watch", "overlay_stats", "overlay_gate_dump",
]


def send(payload):
    with socket.create_connection(("127.0.0.1", PORT), timeout=30) as s:
        s.sendall((payload + "\n").encode())
        s.settimeout(30)
        buf = b""
        while not buf.endswith(b"\n"):
            c = s.recv(1 << 20)
            if not c:
                break
            buf += c
    return buf.decode(errors="replace")


if len(sys.argv) > 2 and sys.argv[2] == "--dump":
    name = sys.argv[3]
    extra = sys.argv[4] if len(sys.argv) > 4 else ""
    payload = '{"cmd":"%s"%s}' % (name, ("," + extra) if extra else "")
    print(send(payload))
    sys.exit(0)

for name in NAMES:
    r = send('{"cmd":"%s"}' % name)
    ok = '"ok":true' in r or '"ok": true' in r
    print(("OK   " if ok else "no   ") + name + ("  " + r[:120] if not ok else ""))
