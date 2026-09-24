"""Installer integration checks. Invoke through test_release.ps1 for card protection."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import winreg

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
META = json.loads((ROOT / "release/version.json").read_text())
RECIPE = json.loads((DIST / "stage/kit/recipe.json").read_text())
RESULTS = []


def check(name, condition):
    RESULTS.append({"check": name, "passed": bool(condition)})
    (DIST / "test-results.json").write_text(json.dumps(RESULTS, indent=2) + "\n")
    print(("PASS " if condition else "FAIL ") + name, flush=True)
    if not condition:
        raise AssertionError(name)


def invoke(args, timeout=180, env=None):
    # Only headless/silent executables are used; no game or installer window.
    return subprocess.run([str(x) for x in args], cwd=ROOT, timeout=timeout, env=env,
                          creationflags=subprocess.CREATE_NO_WINDOW).returncode


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalized_pe_sha(path: Path) -> str:
    data = bytearray(path.read_bytes())
    pe = int.from_bytes(data[0x3C:0x40], "little")
    data[pe + 8:pe + 12] = bytes(4)
    data[pe + 24 + 64:pe + 24 + 68] = bytes(4)
    return hashlib.sha256(bytes(data)).hexdigest()


def built_correctly(install: Path) -> bool:
    game = install / "game"
    try:
        stamp = json.loads((game / "build-stamp.json").read_text())
    except (OSError, ValueError):
        return False
    cache = game / "cache" / RECIPE["kernel"]["cache_dir"]
    return (stamp["version"] == META["version"]
            and normalized_pe_sha(game / "DisruptorRecompiled.exe") == RECIPE["link"]["normalized_sha256"]
            and all((cache / m).is_file() for m in RECIPE["kernel"]["modules"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--disc", type=Path, required=True)
    args = parser.parse_args()
    disc = args.disc.resolve()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{8520B55B-9EBE-4777-BAD5-7B220D97677F}_is1") as key:
            location = winreg.QueryValueEx(key, "InstallLocation")[0]
        raise RuntimeError(f"An existing beta is installed at {location}. Use a disposable VM, or uninstall that test copy before running this suite.")
    except FileNotFoundError:
        pass
    setup = DIST / f'DisruptorRecompiled-{META["version"]}-Setup.exe'
    stage = DIST / "stage/DisruptorLauncher.exe"
    # Keep every ancestor outside the repository: the runtime and recompiler search
    # upwards for development files, which would otherwise mask missing release files.
    work = Path(tempfile.mkdtemp(prefix="Disruptor beta " + uuid.uuid4().hex[:8] + " café "))
    (DIST / "test-location.txt").write_text(str(work) + "\n", encoding="utf-8")
    install = work / "Installed Game"
    profile = work / "Player Profile"
    before = sha(disc)
    check("Source disc is the supported USA image", before == META["disc_sha256"])
    check("Launcher accepts valid image", invoke([stage, "--verify-only", disc]) == 0)
    alias = work / "Raw image.iso"
    os.link(disc, alias)  # read-only alias; no copying or modification of original data
    check("Raw image with .iso extension is accepted", invoke([stage, "--verify-only", alias]) == 0)
    alias.unlink()
    bad = work / "truncated.bin"
    bad.write_bytes(b"not a disc")
    check("Launcher rejects truncated image", invoke([stage, "--verify-only", bad]) == 2)
    corrupt = work / "wrong-hash.iso"
    with corrupt.open("wb") as file:
        file.truncate(META["disc_size"])
    check("Launcher rejects full-size wrong image", invoke([stage, "--verify-only", corrupt]) == 2)
    common = [setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL", "/TASKS=", "/NOICONS"]
    invalid = work / "Rejected Install"
    code = invoke([*common, f"/DIR={invalid}", f"/DISCFILE={corrupt}", f"/LOG={work / 'invalid-install.log'}"])
    check("Installer rejects wrong hash without installing game", code != 0 and not (invalid / "DisruptorLauncher.exe").exists())
    corrupt.unlink()

    started = time.time()
    code = invoke([*common, f"/DIR={install}", f"/DISCFILE={disc}", f"/LOG={work / 'install.log'}"], timeout=900)
    minutes = (time.time() - started) / 60
    check(f"Clean silent installation and build succeed in a path with spaces and Unicode ({minutes:.1f} min)", code == 0)
    launcher = install / "DisruptorLauncher.exe"
    check("Launcher, builder and kit are installed", launcher.is_file() and (install / "DisruptorBuilder.exe").is_file()
          and (install / "kit/recipe.json").is_file())
    check("Game was built on this PC and matches the tested release", built_correctly(install))
    check("Installed disc matches original", sha(install / "disc/Disruptor.bin") == before)
    check("Build left no extracted program, generated C or work files",
          not (install / "work").exists() and not any(install.rglob("*.c")) and not any(install.rglob("SLUS_002.24*")))
    check("Builder sentinel is excluded", not (install / ".release-owned").exists())

    print("Running the installed lean game headlessly for 55 seconds...", flush=True)
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith(("PSX_", "DISRUPTOR_", "SDL_"))}
    clean_env["PATH"] = os.path.join(os.environ["WINDIR"], "System32")
    code = invoke([launcher, "--smoke-test", profile, "55"], timeout=90, env=clean_env)
    check(f"Installed launcher starts game in isolated profile and survives smoke run (exit {code})", code == 0)
    log = (profile / "logs/game-last.log").read_text(encoding="utf-8", errors="replace")
    check("Headless runtime initialized", "headless frontend enabled" in log)
    check("Isolated writable profile selected", "CLI writable-state directory = " + str(profile / "saves") in log)
    check("Original game executable is loaded from supplied disc", "text image guard armed" in log.lower() and ", disc " in log.lower())
    (work / "smoke-evidence.log").write_text(log, encoding="utf-8")
    settings = install / "game/settings.toml"
    binds = install / "game/keybinds.ini"
    check("Launcher wrote runtime settings", "supersampling" in settings.read_text() and (install / "game/launcher.ini").is_file())
    settings.write_text(settings.read_text() + "\n# integration-test preserved display settings\n")
    binds.write_text(binds.read_text() + "\n# integration-test preserved bindings\n")
    saved_settings = sha(settings)
    saved_binds = sha(binds)
    sentinel = profile / "saves/preservation-check.txt"
    sentinel.write_text("player progress remains")
    code = invoke([*common, f"/DIR={install}", f"/LOG={work / 'upgrade.log'}"], timeout=900)
    check("Repair/upgrade reuses installed disc and rebuilds", code == 0 and built_correctly(install))
    check("Repair preserves settings and bindings", sha(settings) == saved_settings and sha(binds) == saved_binds)
    check("Repair preserves saves", sentinel.read_text() == "player progress remains")
    uninstall = install / "unins000.exe"
    code = invoke([uninstall, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={work / 'uninstall.log'}"])
    # The uninstaller may spawn its temporary copy before the original returns.
    for _ in range(100):
        if not launcher.exists() and not (install / "kit").exists():
            break
        time.sleep(0.1)
    check("Uninstall removes installed and built files",
          code == 0 and not launcher.exists() and not (install / "game/DisruptorRecompiled.exe").exists()
          and not (install / "game/cache").exists() and not (install / "kit").exists())
    check("Uninstall preserves saves and personal settings", sentinel.exists() and settings.exists() and binds.exists())
    check("Uninstall removes imported copy and preserves original disc",
          not (install / "disc/Disruptor.bin").exists() and sha(disc) == before)
    print(f"Integration evidence: {work.name}", flush=True)


if __name__ == "__main__":
    main()
