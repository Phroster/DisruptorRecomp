#!/usr/bin/env python3
"""Per-guest-frame GTE command totals: detects whether the game transforms its
3D scene every guest frame (60 Hz) or every other frame (30 Hz)."""
import collections
import time

from input_probe import send

PORT = 4625


def main():
    samples = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 4.0:
        r = send(PORT, '{"cmd":"gte_ring_dump","count":1,"newest":1}')
        e = r["entries"][-1]
        samples.append((e["frame"], r["total"]))
    span = time.perf_counter() - t0

    first_seen = {}
    order = []
    for frame, total in samples:
        if frame not in first_seen:
            first_seen[frame] = total
            order.append(frame)

    print("samples=%d span=%.2fs frames observed=%d" % (len(samples), span, len(order)))
    print("first 24 frames:", order[:24])

    per = []
    for a, b in zip(order, order[1:]):
        per.append((a, first_seen[b] - first_seen[a]))
    hist = collections.Counter()
    for f, n in per:
        if n == 0:
            hist["0"] += 1
        elif n < 200:
            hist["<200"] += 1
        elif n < 2000:
            hist["200-2k"] += 1
        else:
            hist[">2k"] += 1
    print("commands per frame histogram:", dict(hist))
    print("sample per-frame counts:", [n for _, n in per[:24]])

    gaps = []
    prev_t = None
    for frame, total in samples:
        if prev_t is not None and frame != prev_t[0]:
            gaps.append(frame - prev_t[0])
        prev_t = (frame, total)
    print("frame-number gaps:", collections.Counter(gaps))


if __name__ == "__main__":
    main()
