"""Capture a bounded diagnostic snapshot from the running baseline (localhost only)."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "psxrecomp/tools"))
import debug_client  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4624)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--name", default="baseline")
    args = parser.parse_args()
    if not 0 < args.seconds <= 30 or not args.name.replace("-", "").replace("_", "").isalnum():
        parser.error("Use 0 < seconds <= 30 and an alphanumeric capture name.")
    output = ROOT / "captures"
    output.mkdir(exist_ok=True)

    def query(command, **fields):
        # Close after each response so the game never waits on an idle client.
        with debug_client.connect(port=args.port) as connection:
            result = debug_client.send_cmd(connection, {"id": 1, "cmd": command, **fields})
        if not result.get("ok"):
            raise RuntimeError(f"{command}: {result}")
        return result

    first = query("frame")
    start = time.monotonic()
    time.sleep(args.seconds)
    last = query("frame")
    elapsed = time.monotonic() - start
    report = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "interval_seconds": elapsed,
        "host_frames_advanced": last["frame"] - first["frame"],
        "note": "Host frame progress is not a measurement of unique gameplay frames.",
    }
    for command in ("gpu", "unknown_dispatch_log", "spu_status", "autocompile_status"):
        # The wire command corresponding to the CLI's 'gpu' alias is gpu_state.
        wire_command = "gpu_state" if command == "gpu" else command
        report[command] = query(wire_command)
    report["screenshot"] = query("screenshot", path=(output / f"{args.name}.png").as_posix())
    target = output / f"{args.name}.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {target}")
    print(f"Host frames advanced: {report['host_frames_advanced']} in {elapsed:.2f}s")
    print(f"Missing dispatches: {report['unknown_dispatch_log']['total']}")


if __name__ == "__main__":
    main()
