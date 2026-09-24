#!/usr/bin/env python3
"""Measure the game's own 3D scene update rate: poll the newest GTE camera
matrix rapidly and count distinct poses per second, plus the yaw byte."""
import time

from input_probe import load_state, send

YAW = 0x80077624


def newest_rt(port):
    r = send(port, '{"cmd":"gte_ring_dump","count":1,"newest":1}')
    e = r["entries"][-1]
    return tuple(e["RT"]), r.get("total")


def yaw(port):
    r = send(port, '{"cmd":"read_ram","addr":"0x%X","len":1}' % YAW)
    return int(r["hex"], 16)


def main():
    port = 4624
    load_state(port, 3)
    time.sleep(1.0)

    samples = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 4.0:
        rt, total = newest_rt(port)
        samples.append((time.perf_counter() - t0, rt, total))
        time.sleep(0.004)

    changes = []
    for (t1, m1, _), (t2, m2, _) in zip(samples, samples[1:]):
        if m1 != m2:
            changes.append(t2)
    span = samples[-1][0] - samples[0][0]
    print("samples=%d span=%.2fs distinct-matrix changes=%d -> %.1f Hz" %
          (len(samples), span, len(changes), len(changes) / span))

    if len(changes) > 1:
        gaps = [b - a for a, b in zip(changes, changes[1:])]
        gaps.sort()
        print("pose interval ms: p10=%.1f p50=%.1f p90=%.1f" % (
            gaps[int(len(gaps) * .1)] * 1000,
            gaps[int(len(gaps) * .5)] * 1000,
            gaps[int(len(gaps) * .9)] * 1000))

    totals = [t for _, _, t in samples if t is not None]
    if totals:
        print("ring total start=%s end=%s (%d draws in %.2fs -> %.1f Hz)" %
              (totals[0], totals[-1], totals[-1] - totals[0], span,
               (totals[-1] - totals[0]) / span))


if __name__ == "__main__":
    main()
