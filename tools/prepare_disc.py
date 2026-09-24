"""Prepare the original EXE using only our supplied disc and generic PSXRecomp tools."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BIN_HASH = "3b49f9874e30c613ca9d17720716764cd76d0ac968c0acd0f53159366c0cf3a4"
EXE_HASH = "48e8c3143b7f5de10340c9d4a9bac8cb7e97c15eda7a0897d3cf337ad96cb2c4"


def main():
    disc = ROOT / "disc"
    cue, binary = disc / "Disruptor.cue", disc / "Disruptor.bin"
    if not cue.is_file() or not binary.is_file():
        sys.exit("Put Disruptor.bin and Disruptor.cue in disc/ first.")
    with binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != BIN_HASH:
        sys.exit(f"Unsupported disc SHA-256: {digest}\nExpected: {BIN_HASH}")
    local = ROOT / ".local"
    inputs = ROOT / "input"
    local.mkdir(exist_ok=True)
    inputs.mkdir(exist_ok=True)
    probe_json = local / "disc-probe.json"
    subprocess.run([
        sys.executable, str(ROOT / "psxrecomp/tools/new_project_layout/probe_disc.py"),
        str(cue), "--json-out", str(probe_json),
        "--write-boot-exe", str(inputs), "--players", "1",
        "--write-seeds", str(inputs / "functions.txt"),
    ], cwd=ROOT, check=True)
    probe = json.loads(probe_json.read_text(encoding="utf-8"))
    exe = (inputs / "SLUS_002.24").read_bytes()
    if hashlib.sha256(exe).hexdigest() != EXE_HASH or exe[:8] != b"PS-X EXE":
        sys.exit("Extracted executable does not match supported SLUS-00224.")
    offsets = {"entry_pc": 0x10, "load_address": 0x18, "text_size": 0x1C, "stack_base": 0x30}
    config = tomllib.loads((ROOT / "game.toml").read_text(encoding="utf-8"))["game"]
    observed = {key: struct.unpack_from("<I", exe, offset)[0] for key, offset in offsets.items()}
    for key, actual in observed.items():
        if int(config[key], 0) != actual:
            sys.exit(f"game.toml {key} differs from the actual EXE header: {actual:#x}")
    if len(exe) < 2048 + observed["text_size"]:
        sys.exit("The executable payload is truncated.")
    print(json.dumps({"source": "original disc EXE header", **{k: hex(v) for k, v in observed.items()}}, indent=2))
    print(f"Verified {probe['serial']}; original EXE retained unchanged; {probe['seed_count']} first-pass function seeds.")


if __name__ == "__main__":
    main()
