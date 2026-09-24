#!/usr/bin/env python3
"""Watch for the damage-flash effect and freeze the evidence.

Polls the runtime's present_shot, detects a red-tinted full-screen effect in
the centre band (the game's damage flash), and when it trips dumps the
ws_census window around the current frame plus the triggering capture, so the
offending primitive(s) can be identified from src_addr.

Usage: python tools/flash_watch.py [--port 4624] [--out logs/flash]
                                   [--interval 0.5] [--seconds 900]
"""
import argparse
import json
import os
import socket
import time

from PIL import Image


def send(port, payload):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall((payload + "\n").encode())
        s.settimeout(5)
        data = b""
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


def parse_json(text):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                continue
    return None


def red_metric(path):
    img = Image.open(path).convert("RGB")
    w, h = img.size
    # centre half of the frame, middle vertical band
    x0, x1 = w // 4, 3 * w // 4
    y0, y1 = h // 4, 3 * h // 4
    crop = img.crop((x0, y0, x1, y1)).resize((64, 48))
    px = list(crop.getdata())
    r = sum(p[0] for p in px) / len(px)
    g = sum(p[1] for p in px) / len(px)
    b = sum(p[2] for p in px) / len(px)
    return r - g, (r, g, b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=4624)
    ap.add_argument("--out", default="logs/flash")
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--seconds", type=float, default=900.0)
    ap.add_argument("--threshold", type=float, default=35.0)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    deadline = time.time() + args.seconds
    n = 0
    armed = True
    while time.time() < deadline:
        path = os.path.join(args.out, f"cap_{n:04d}.png").replace("\\", "/")
        try:
            send(args.port, '{"cmd":"present_shot","path":"%s"}' % path)
            time.sleep(0.4)
            send(args.port, '{"cmd":"present_shot_seq"}')
            if not os.path.exists(path):
                n += 1
                time.sleep(args.interval)
                continue
            metric, rgb = red_metric(path)
            if armed and metric > args.threshold:
                st = parse_json(send(args.port, '{"cmd":"gpu_state"}'))
                frame = int(st.get("cur_frame", 0)) if st else 0
                send(args.port,
                     '{"cmd":"ws_census","start":%d,"end":%d,"out":"logs/flash_census.csv"}'
                     % (max(0, frame - 150), frame + 10))
                keep = os.path.join(args.out, "FLASH.png")
                Image.open(path).save(keep)
                print(f"FLASH n={n} frame={frame} metric={metric:.1f} rgb={tuple(int(v) for v in rgb)}",
                      flush=True)
                armed = False
            elif not armed and metric < args.threshold * 0.4:
                armed = True
        except Exception as exc:
            print("err", exc, flush=True)
        n += 1
        time.sleep(args.interval)
    print("done", n, flush=True)


if __name__ == "__main__":
    main()
