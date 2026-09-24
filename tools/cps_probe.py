#!/usr/bin/env python3
"""Arm/dump the CPS interior-continuation dispatch probe.

Usage: python tools/cps_probe.py <port> [addr]
"""
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4634
ADDR = sys.argv[2] if len(sys.argv) > 2 else None

payload = ('{"cmd":"overlay_cps_probe","addr":"%s"}' % ADDR) if ADDR \
    else '{"cmd":"overlay_cps_probe"}'

with socket.create_connection(("127.0.0.1", PORT), timeout=30) as s:
    s.sendall((payload + "\n").encode())
    s.settimeout(30)
    buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(1 << 20)
        if not c:
            break
        buf += c
print(payload)
print(buf.decode(errors="replace")[:1200])
