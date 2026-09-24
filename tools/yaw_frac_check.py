#!/usr/bin/env python3
"""Check the fractional yaw accumulator: many small mouse counts must add up to
the same total as one large count (no per-frame rounding loss), and pad turning
must resync cleanly."""
import time

from input_probe import load_state, send

YAW = 0x80077624


def yaw(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % YAW)
    return int(r["hex"], 16)


def delta(before, after):
    d = (after - before) % 256
    return d - 256 if d > 127 else d


def main():
    port = 4624
    load_state(port, 3)
    time.sleep(1.0)
    base = yaw(port)
    print("baseline yaw:", base, flush=True)

    for _ in range(5):
        send(port, '{"cmd":"host_mouse","dx":1}')
        time.sleep(0.08)
    mid = yaw(port)
    exp5 = 5 * 0.30 / (360.0 / 256.0)
    print(f"5x dx=1 : {base} -> {mid} (delta {delta(base, mid):+d}, expected {exp5:+.1f})",
          flush=True)

    for _ in range(10):
        send(port, '{"cmd":"host_mouse","dx":1}')
        time.sleep(0.08)
    end = yaw(port)
    exp15 = 15 * 0.30 / (360.0 / 256.0)
    print(f"15x dx=1: {base} -> {end} (delta {delta(base, end):+d}, expected {exp15:+.1f})",
          flush=True)

    send(port, '{"cmd":"host_mouse","dx":50}')
    time.sleep(0.2)
    big = yaw(port)
    exp = 50 * 0.30 / (360.0 / 256.0)
    print(f"1x dx=50: {end} -> {big} (delta {delta(end, big):+d}, expected {exp:+.1f})",
          flush=True)

    send(port, '{"cmd":"set_input","buttons":65503}')
    time.sleep(0.35)
    send(port, '{"cmd":"clear_input"}')
    time.sleep(0.2)
    turned = yaw(port)
    print("after pad turn:", turned, flush=True)
    send(port, '{"cmd":"host_mouse","dx":10}')
    time.sleep(0.2)
    after = yaw(port)
    exp10 = 10 * 0.30 / (360.0 / 256.0)
    print(f"post-turn dx=10: {turned} -> {after} "
          f"(delta {delta(turned, after):+d}, expected {exp10:+.1f})", flush=True)


if __name__ == "__main__":
    main()
