#!/usr/bin/env python3
"""Game logic/camera tick rate: hold the turn button and sample the yaw byte
at high frequency; the byte only changes on a game tick."""
import time

from input_probe import send

YAW = 0x80077624


def yaw(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % YAW)
    return int(r["hex"], 16)


def main():
    port = 4624
    send(port, '{"cmd":"set_input","buttons":65503}')
    time.sleep(0.3)

    samples = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 3.0:
        samples.append((time.perf_counter() - t0, yaw(port)))
        time.sleep(0.002)
    send(port, '{"cmd":"clear_input"}')

    changes = [t2 for (t1, y1), (t2, y2) in zip(samples, samples[1:]) if y1 != y2]
    span = samples[-1][0] - samples[0][0]
    print("samples=%d span=%.2fs yaw changes=%d -> %.1f Hz" %
          (len(samples), span, len(changes), len(changes) / span))
    if len(changes) > 1:
        gaps = sorted(b - a for a, b in zip(changes, changes[1:]))
        print("tick interval ms: p10=%.1f p50=%.1f p90=%.1f max=%.1f" % (
            gaps[int(len(gaps) * .1)] * 1000, gaps[len(gaps) // 2] * 1000,
            gaps[int(len(gaps) * .9)] * 1000, gaps[-1] * 1000))


if __name__ == "__main__":
    main()
