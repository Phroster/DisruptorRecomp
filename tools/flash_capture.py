#!/usr/bin/env python3
"""Poll the runtime's present_shot into a directory so transient effects (damage
flash, fades) can be analysed after the fact.

Usage: python tools/flash_capture.py [--port 4624] [--out logs/flash]
                                     [--interval 0.7] [--seconds 180]
"""
import argparse
import os
import socket
import time


def send(port, obj):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall((obj + "\n").encode())
        data = b""
        s.settimeout(5)
        try:
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
        except socket.timeout:
            pass
        return data.decode(errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--out", default="logs/flash")
    ap.add_argument("--interval", type=float, default=0.7)
    ap.add_argument("--seconds", type=float, default=180.0)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    deadline = time.time() + args.seconds
    n = 0
    while time.time() < deadline:
        path = os.path.join(args.out, f"cap_{n:04d}.png").replace("\\", "/")
        try:
            send(args.port, '{"cmd":"present_shot","path":"%s"}' % path)
            time.sleep(0.35)
            send(args.port, '{"cmd":"present_shot_seq"}')
        except Exception as exc:  # keep the loop alive across reconnects
            print("err", exc, flush=True)
        n += 1
        time.sleep(args.interval)
    print("done", n, flush=True)


if __name__ == "__main__":
    main()
