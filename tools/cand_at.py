#!/usr/bin/env python3
"""overlay_candidates at one PC (includes the device_touch flag).

Usage: python tools/cand_at.py <port> <pc-hex> [lazy]
"""
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4634
PC = sys.argv[2] if len(sys.argv) > 2 else "0xB0"
LAZY = (len(sys.argv) > 3 and sys.argv[3] == "lazy")

payload = '{"cmd":"overlay_candidates","pc":"%s"%s}' % (
    PC, ',"lazy":1' if LAZY else "")

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
print(buf.decode(errors="replace")[:3000])
