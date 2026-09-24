#!/usr/bin/env python3
"""Print only the head (counters) of the overlay_native_ring reply.

Usage: python tools/ring_head.py [port]
"""
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4634

with socket.create_connection(("127.0.0.1", PORT), timeout=60) as s:
    s.sendall(b'{"cmd":"overlay_native_ring"}\n')
    s.settimeout(60)
    buf = b""
    while b'"recent"' not in buf and not buf.endswith(b"\n"):
        c = s.recv(1 << 20)
        if not c:
            break
        buf += c
t = buf.decode(errors="replace")
i = t.find('"recent"')
print(t[:i + 10] if i > 0 else t[:2000])
