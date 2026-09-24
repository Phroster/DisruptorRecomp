#!/usr/bin/env python3
"""Measure the game's logic tick rate (yaw byte changes while turning) at high
sampling resolution, with an interval histogram to distinguish 60 Hz timer from
vblank-count-driven logic."""
import collections
import sys
import time

from input_probe import send

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4625
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
YAW = 0x80077624


def yaw(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % YAW)
    return int(r["hex"], 16)


def main():
    send(PORT, '{"cmd":"set_input","buttons":65503}')
    time.sleep(0.3)
    samples = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < DUR:
        samples.append((time.perf_counter() - t0, yaw(PORT)))
    send(PORT, '{"cmd":"clear_input"}')

    changes = [(t2 - t1, t2) for (t1, y1), (t2, y2) in zip(samples, samples[1:])
               if y1 != y2]
    span = samples[-1][0] - samples[0][0]
    rate = len(changes) / span
    print("samples=%d (%.1f/s) span=%.2fs  yaw changes=%d -> %.1f Hz" %
          (len(samples), len(samples) / span, span, len(changes), rate))
    gaps = sorted(g for g, _ in changes)
    if gaps:
        p = lambda q: gaps[min(len(gaps) - 1, int(len(gaps) * q))]
        print("inter-change ms: p10=%.1f p50=%.1f p90=%.1f max=%.1f" %
              (p(.1) * 1000, p(.5) * 1000, p(.9) * 1000, gaps[-1] * 1000))
    v = send(PORT, '{"cmd":"vblank_rate"}')
    print("vblanks delivered:", v["delivered"], "raise:", v["cycle_paced_raise"])


if __name__ == "__main__":
    main()
