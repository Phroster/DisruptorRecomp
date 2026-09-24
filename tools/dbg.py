#!/usr/bin/env python3
"""Query several debug commands over one connection and print raw JSON."""
import json
import socket
import sys
import time


def connect(port):
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    return s


def ask(s, payload, timeout=10.0):
    s.sendall((payload + "\n").encode())
    s.settimeout(timeout)
    buf = b""
    while True:
        try:
            chunk = s.recv(1 << 20)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        if buf.rstrip().endswith(b"}"):
            break
    for line in buf.decode(errors="replace").splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    return {"raw": buf.decode(errors="replace")[:300]}


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4624
    s = connect(port)
    print("ping:", ask(s, '{"cmd":"ping"}'), flush=True)
    for payload in sys.argv[2:]:
        print(f"--- {payload}", flush=True)
        print(json.dumps(ask(s, payload), indent=1)[:4000], flush=True)
        time.sleep(0.2)
    s.close()


if __name__ == "__main__":
    main()
