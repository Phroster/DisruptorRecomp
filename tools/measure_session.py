#!/usr/bin/env python3
"""Controlled performance sample: while the savestate's gameplay is still
fresh, poll latency / frame_perf / gl_present_ring and summarize.

Usage: python tools/measure_session.py [--port 4624] [--seconds 45]
"""
import os
import json
import statistics
import sys
import time

from ask import ask

PORT = 4624
LOGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


def sample_latency():
    r = ask(PORT, json.dumps({"cmd": "latency"}))
    s = r.get("summary")
    if not s:
        return None
    fp = s.get("frame_period", {})
    return {
        "p50": fp.get("p50_us"), "p95": fp.get("p95_us"),
        "max": fp.get("max_us"), "min": fp.get("min_us"),
        "input_to_swap_p50": s.get("input_to_swap", {}).get("p50_us"),
        "input_to_swap_p95": s.get("input_to_swap", {}).get("p95_us"),
        "present_mode": s.get("present_mode"),
    }


def sample_frame_perf():
    r = ask(PORT, json.dumps({"cmd": "frame_perf"}))
    if not r.get("ok"):
        return {"error": r.get("error")}
    a = r.get("all", {})
    return {
        "emu_cpu_avg": a.get("emu_cpu_ms_avg"), "emu_cpu_max": a.get("emu_cpu_ms_max"),
        "scene_gpu_avg": a.get("scene_gpu_ms_avg"), "scene_gpu_max": a.get("scene_gpu_ms_max"),
        "present_gpu_avg": a.get("present_gpu_ms_avg"), "present_gpu_max": a.get("present_gpu_ms_max"),
        "total_avg": a.get("total_ms_avg"), "total_max": a.get("total_ms_max"),
        "prims_avg": a.get("prims_avg"), "wide_frames": r.get("wide_frames"),
    }


def sample_present_ring():
    r = ask(PORT, json.dumps({"cmd": "gl_present_ring", "n": 600}))
    events = r.get("events") if isinstance(r, dict) else None
    if not events:
        return {"error": r.get("error", "no events")}
    return {"events": events}


def dump_ring(cmd, extra=None, tag=""):
    payload = {"cmd": cmd}
    if extra:
        payload.update(extra)
    r = ask(PORT, json.dumps(payload))
    path = os.path.join(LOGS, f"{cmd}{tag}.json")
    with open(path, "w") as fh:
        json.dump(r, fh)
    n = len(r.get("events", r.get("entries", []))) if isinstance(r, dict) else 0
    print(f"           saved {cmd}{tag} ({n} rows)", flush=True)


def main():
    seconds = 45
    if "--seconds" in sys.argv:
        seconds = int(sys.argv[sys.argv.index("--seconds") + 1])
    end = time.time() + seconds
    ring_saved = 0
    while time.time() < end:
        lat = sample_latency()
        fp = sample_frame_perf()
        print(f"[{time.strftime('%H:%M:%S')}] latency={lat}", flush=True)
        print(f"           frame_perf={fp}", flush=True)
        if ring_saved < 2:
            ring = sample_present_ring()
            if "events" in ring:
                path = os.path.join(LOGS, f"gl_present_ring_{ring_saved}.json")
                with open(path, "w") as fh:
                    json.dump(ring["events"], fh)
                print(f"           saved {path} ({len(ring['events'])} events)", flush=True)
                ring_saved += 1
            else:
                print(f"           ring: {ring}", flush=True)
        if ring_saved:
            try:
                dump_ring("starv_ring", {"count": 32}, f"_{ring_saved}")
                dump_ring("gl_coh_ring", {"n": 128}, f"_{ring_saved}")
                dump_ring("data_shards", None, f"_{ring_saved}")
            except Exception as exc:
                print("           ring dump failed:", exc, flush=True)
        time.sleep(9)
    print("done", flush=True)


if __name__ == "__main__":
    main()
