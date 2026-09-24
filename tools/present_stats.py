#!/usr/bin/env python3
"""Present cadence summary from the live instance's GL present ring."""
import statistics
import sys

from input_probe import send


def main():
    port = 4624
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 720
    r = send(port, '{"cmd":"gl_present_ring","count":%d}' % n)
    entries = r.get("entries") or r.get("ring") or []
    stamps = []
    for e in entries:
        t = e.get("t_us") or e.get("us") or e.get("ts_us")
        if t is None:
            for k in ("present_us", "time_us", "timestamp_us"):
                if k in e:
                    t = e[k]
                    break
        if t is not None:
            stamps.append(int(t))
    if not stamps:
        print("keys:", sorted(entries[-1].keys()) if entries else r.keys())
        print(r if not entries else entries[-1])
        return
    stamps.sort()
    d = [b - a for a, b in zip(stamps, stamps[1:]) if 0 < b - a < 100000]
    d.sort()
    if not d:
        print("no usable intervals")
        return
    p = lambda q: d[min(len(d) - 1, int(len(d) * q))]
    print("presents=%d  span=%.2fs  rate=%.1f Hz" %
          (len(stamps), (stamps[-1] - stamps[0]) / 1e6,
           len(stamps) / ((stamps[-1] - stamps[0]) / 1e6)))
    print("interval us: p50=%d p90=%d p99=%d max=%d  mean=%.0f sd=%.0f" %
          (p(.5), p(.9), p(.99), d[-1], statistics.mean(d),
           statistics.pstdev(d)))


if __name__ == "__main__":
    main()
