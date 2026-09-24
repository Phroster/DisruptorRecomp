#!/usr/bin/env python3
"""Summarize a psxrecomp ws_census CSV for the widescreen audit.

Usage: python tools/census_report.py <census.csv> [--disp-w 320] [--top 20]

The census records every drawn primitive with the guest PC that emitted it
(`src_addr`), the raw (pre-draw_offset) screen-X extent across its position
vertices, and whether the prim is tagged by the game's sprite funnel. For a
native-wide 16:9 audit the question is: does world geometry reach beyond the
canonical 4:3 edge (x >= disp_w), and if not, which emitter stops at it?
"""
import argparse
import csv
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--disp-w", type=int, default=320)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    rows = []
    with open(args.csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    if not rows:
        print("no rows")
        return

    frames = [int(r["frame"]) for r in rows]
    print(f"rows={len(rows)} frames={min(frames)}..{max(frames)} disp_w={args.disp_w}")

    total_over = 0
    per_addr = defaultdict(lambda: {
        "n": 0, "untagged": 0, "xmin": 0x7FFF, "xmax": -0x8000,
        "over_right": 0, "over_left": 0, "ops": defaultdict(int),
    })

    for r in rows:
        addr = r["src_addr"]
        xmin = int(r["xmin"])
        xmax = int(r["xmax"])
        tagged = int(r["tagged"])
        op = r["opcode"]
        d = per_addr[addr]
        d["n"] += 1
        if not tagged:
            d["untagged"] += 1
        d["xmin"] = min(d["xmin"], xmin)
        d["xmax"] = max(d["xmax"], xmax)
        d["ops"][op] += 1
        if xmax > args.disp_w:
            d["over_right"] += 1
            if not tagged:
                total_over += 1
        if xmin < 0:
            d["over_left"] += 1

    print(f"untagged prims with xmax > {args.disp_w}: {total_over}")

    ranked = sorted(per_addr.items(), key=lambda kv: kv[1]["n"], reverse=True)
    print(f"\n-- top {args.top} emitters by prim count --")
    print(f"{'src_addr':>12} {'prims':>7} {'untag':>7} {'xmin':>7} {'xmax':>7} "
          f"{'>W':>7} {'<0':>7}  ops")
    for addr, d in ranked[:args.top]:
        ops = ",".join(f"{k}:{v}" for k, v in sorted(d["ops"].items(), key=lambda kv: -kv[1])[:3])
        print(f"{addr:>12} {d['n']:>7} {d['untagged']:>7} {d['xmin']:>7} "
              f"{d['xmax']:>7} {d['over_right']:>7} {d['over_left']:>7}  {ops}")


if __name__ == "__main__":
    main()
