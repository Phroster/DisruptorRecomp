#!/usr/bin/env python3
"""Capture a frame-pacing diagnostic bundle from the running game.

Usage: python tools/diag_capture.py --out <file.json> [--seconds 45] [--port 4624]

Samples the always-on rings (latency, frame_perf, phase_profile, dispatch and
dirty-RAM counters, GL present ring, VBlank rate) while you play, then writes
one JSON file. Run it after you are IN gameplay and keep moving/turning.
"""
import json
import sys
import time

from ask import ask

PORT = 4624


def q(cmd, **kw):
    d = {"cmd": cmd}
    d.update(kw)
    return ask(PORT, json.dumps(d), timeout=10.0, tries=3)


def main():
    global PORT
    args = sys.argv[1:]
    out = args[args.index("--out") + 1] if "--out" in args else "disruptor-diag.json"
    secs = int(args[args.index("--seconds") + 1]) if "--seconds" in args else 45
    if "--port" in args:
        PORT = int(args[args.index("--port") + 1])

    bundle = {"port": PORT, "seconds": secs, "samples": [], "start": time.time()}
    bundle["ping"] = q("ping")
    bundle["gl_interp_start"] = q("gl_interp")
    bundle["overlay_loader_start"] = q("overlay_loader_status")
    bundle["dirty_ram_start"] = q("dirty_ram_stats")
    bundle["game_options"] = q("game_options")
    end = time.time() + secs
    n = 0
    while time.time() < end:
        s = {
            "t": round(time.time() - bundle["start"], 1),
            "latency": q("latency", window=300, raw=1, count=300),
            "frame_perf": q("frame_perf"),
            "phase_profile": q("phase_profile", window=5),
            "vblank_rate": q("vblank_rate"),
        }
        lat = s["latency"].get("summary", {}).get("frame_period", {})
        print(f"[{n}] frame_period p50={lat.get('p50_us')} p95={lat.get('p95_us')} "
              f"max={lat.get('max_us')} us", flush=True)
        bundle["samples"].append(s)
        n += 1
        time.sleep(5)
    bundle["gl_present_ring"] = q("gl_present_ring", n=1200)
    bundle["present_ring"] = q("present_ring", n=600)
    bundle["starv_ring"] = q("starv_ring", count=64)
    bundle["phase_hot"] = q("phase_hot")
    bundle["overlay_loader_end"] = q("overlay_loader_status")
    bundle["dirty_ram_end"] = q("dirty_ram_stats")
    bundle["dispatch_stats"] = q("dispatch_stats")
    bundle["timers_state"] = q("timers_state")
    ev = bundle["gl_present_ring"].get("events") or []
    if len(ev) > 2:
        frames = [e[1] for e in ev]
        steps = [b - a for a, b in zip(frames, frames[1:])]
        dropped = sum(s - 1 for s in steps if s > 1)
        print(f"presents: {len(ev)}  guest frames not presented: {dropped} "
              f"({100.0 * dropped / max(1, len(ev) + dropped):.1f}%)", flush=True)
        bundle["dropped_frames"] = {"presents": len(ev), "dropped": dropped}
    with open(out, "w") as fh:
        json.dump(bundle, fh)
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
