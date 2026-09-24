#!/usr/bin/env python3
"""Query debug commands (name + key=value pairs) with retry.

Usage: python ask.py frame_perf "latency" ...
       python ask.py ws_margin value=200
"""
import json
import socket
import sys
import time


def build(tokens):
    cmd = tokens[0]
    d = {"cmd": cmd}
    for tok in tokens[1:]:
        if "=" in tok:
            k, v = tok.split("=", 1)
            try:
                d[k] = int(v, 0)
            except ValueError:
                d[k] = v
    return json.dumps(d)


def ask(port, payload, timeout=20.0, tries=8):
    last = None
    for _ in range(tries):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
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
                text = buf.decode(errors="replace")
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            return json.loads(line)
                        except Exception:
                            continue
                return {"raw": text[:400]}
        except Exception as exc:
            last = str(exc)
            time.sleep(0.5)
    return {"error": last}


def main():
    port = 4624
    groups = []
    cur = []
    for a in sys.argv[1:]:
        if "=" in a or " " not in a and a.islower() and not a.startswith("-"):
            cur.append(a)
            if len(cur) == 1 and "=" in a:
                cur = [a]
        else:
            cur.append(a)
    # simpler: treat argv as a flat list of tokens; a bare word starts a command
    cmds = []
    buf = []
    for tok in sys.argv[1:]:
        if "=" not in tok:
            if buf:
                cmds.append(buf)
            buf = [tok]
        else:
            buf.append(tok)
    if buf:
        cmds.append(buf)

    for tokens in cmds:
        payload = build(tokens)
        r = ask(port, payload)
        print("=" * 8, payload)
        print(json.dumps(r, indent=1)[:8000], flush=True)


if __name__ == "__main__":
    main()
