"""Build the offline, per-user Windows installer.

The installer carries no game code or game data. It ships the prebuilt framework
runtime, the recompiler, a trimmed copy of the project's GCC toolchain, a private
Python for the framework's kernel-code compiler, and kit/recipe.json. On the
player's PC, release/builder.cpp rebuilds the game from their own disc and checks
every stage against the recipe, which records fingerprints of this tested build.

Builder prerequisites: the verified lean play build (build.ps1), the tested kernel
cache (warm_cache.ps1), Python 3.11+ with Pillow, the WinLibs GCC 15.2 (UCRT)
toolchain on PATH, CMake + Ninja, and Inno Setup 7. Players need none of these.
"""
from __future__ import annotations
import argparse
import base64
import codecs
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile
import zlib
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = DIST / "release-build"
STAGE = DIST / "stage"
KIT = STAGE / "kit"
META = json.loads((ROOT / "release/version.json").read_text())
TRIPLE = "x86_64-w64-mingw32"
EXE_NAME = "SLUS_002.24"
PLAY = ROOT / "build-play"
TESTED_CAPTURES = ["overlay_captures.json", "overlay_captures_gates.json", "overlay_captures_boot.json"]  # warm_cache.ps1 order
KERNEL_FLAVOR = 2
SYSTEM_DIR = Path(os.environ["WINDIR"]) / "System32"


def run(*args, **kwargs):
    kwargs.setdefault("cwd", ROOT)
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def output(*args, **kwargs) -> str:
    return run(*args, capture_output=True, text=True, **kwargs).stdout


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def crc_hex(data: bytes) -> str:
    return "%08X" % (zlib.crc32(data) & 0xFFFFFFFF)


def normalized_pe_sha(path: Path) -> str:
    """Same as normalizedPeSha256 in common.hpp: ignore link timestamp and checksum."""
    data = bytearray(path.read_bytes())
    pe = int.from_bytes(data[0x3C:0x40], "little")
    data[pe + 8:pe + 12] = bytes(4)
    data[pe + 24 + 64:pe + 24 + 68] = bytes(4)
    return sha_bytes(bytes(data))


def reset_owned(path: Path):
    # Never follow a staging junction or delete outside this repository's dist.
    if path.is_symlink() or path.is_junction() or path.resolve().parent != DIST.resolve():
        raise RuntimeError(f"Unsafe staging target: {path}")
    if path.exists():
        if not (path / ".release-owned").is_file():
            raise RuntimeError(f"Refusing to replace unowned directory: {path}")
        for sub in path.rglob("*"):
            if sub.is_symlink() or sub.is_junction():
                raise RuntimeError(f"Refusing to remove staging link: {sub}")
        shutil.rmtree(path)
    path.mkdir(parents=True)
    (path / ".release-owned").touch()


def copy(src: str | Path, dest: str | Path):
    src = Path(src)
    if not src.is_absolute():
        src = ROOT / src
    target = STAGE / dest
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)


def toolchain_root() -> Path:
    gcc = shutil.which("gcc")
    if not gcc:
        raise RuntimeError("gcc is not on PATH")
    return Path(gcc).resolve().parent.parent


TC = toolchain_root()
GCC_VERSION = output(TC / "bin/gcc.exe", "-dumpversion").strip()
LIBEXEC = Path("libexec/gcc") / TRIPLE / GCC_VERSION


def tool_env() -> dict:
    # Put the toolchain first so no older MinGW DLLs (for example Git's) are picked up.
    env = os.environ.copy()
    env["PATH"] = str(TC / "bin") + os.pathsep + env.get("PATH", "")
    return env


# ------------------------------------------------------------------ command lines
def win_split(s: str) -> list[str]:
    """Split a Windows command line the way the MSVCRT/MinGW argv parser does."""
    args, i, n = [], 0, len(s)
    while i < n:
        while i < n and s[i] in " \t":
            i += 1
        if i >= n:
            break
        arg, quoted = "", False
        while i < n and (quoted or s[i] not in " \t"):
            c = s[i]
            if c == "\\":
                j = i
                while j < n and s[j] == "\\":
                    j += 1
                if j < n and s[j] == '"':
                    arg += "\\" * ((j - i) // 2)
                    if (j - i) % 2:
                        arg += '"'
                        i = j + 1
                    else:
                        i = j
                else:
                    arg += "\\" * (j - i)
                    i = j
                continue
            if c == '"':
                if quoted and i + 1 < n and s[i + 1] == '"':
                    arg += '"'
                    i += 2
                    continue
                quoted = not quoted
                i += 1
                continue
            arg += c
            i += 1
        args.append(arg)
    return args


class Ninja:
    """Just enough of build.ninja to read CMake's compile and link statements."""

    def __init__(self, path: Path):
        text = path.read_text(encoding="utf-8").replace("$\n", "")
        self.builds = []
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1
            if not line.startswith("build "):
                continue
            variables = {}
            while i < len(lines) and lines[i].startswith("  "):
                key, _, value = lines[i].strip().partition(" = ")
                variables[key] = self.unescape(value)
                i += 1
            outputs, rule, inputs = self.parse_build(line[6:])
            self.builds.append({"outputs": outputs, "rule": rule, "inputs": inputs, "vars": variables})

    @staticmethod
    def unescape(value: str) -> str:
        return re.sub(r"\$([ :$])", r"\1", value)

    @staticmethod
    def tokens(s: str) -> list[str]:
        out, cur, i = [], "", 0
        while i < len(s):
            if s[i] == "$" and i + 1 < len(s) and s[i + 1] in " :$":
                cur += s[i + 1]
                i += 2
            elif s[i] == " ":
                if cur:
                    out.append(cur)
                cur = ""
                i += 1
            else:
                cur += s[i]
                i += 1
        if cur:
            out.append(cur)
        return out

    def parse_build(self, s: str):
        i = 0
        while True:  # the first unescaped colon ends the output list
            i = s.index(":", i)
            if s[i - 1] != "$":
                break
            i += 1
        outputs = self.tokens(s[:i])
        rest = self.tokens(s[i + 1:])
        rule = rest[0]
        explicit = []
        for tok in rest[1:]:
            if tok in ("|", "||", "|@"):
                break
            explicit.append(tok)
        return outputs, rule, explicit

    def find(self, predicate):
        return [b for b in self.builds if predicate(b)]


def play_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else PLAY / path


# ------------------------------------------------------------------ preflight
def preflight():
    for patch in sorted((ROOT / "patches").glob("*.patch")):
        run("git", "-C", "psxrecomp", "apply", "--reverse", "--check", patch)
    for path in [PLAY / "CMakeCache.txt", PLAY / "DisruptorRecompiled.exe"]:
        if not path.is_file():
            raise RuntimeError("Build the lean play executable first (build.ps1)")
    cache = (PLAY / "CMakeCache.txt").read_text()
    if "PSX_DEBUG_TOOLS:BOOL=OFF" not in cache:
        raise RuntimeError("Refusing an unverified or diagnostic build")
    if "DISRUPTOR_PGXP:BOOL=ON" not in cache:
        raise RuntimeError("The release requires the PGXP build")
    # Bring the play build up to date with its sources (a no-op when it already is).
    # A dry run cannot tell: CMake's glob check always reports a re-run.
    run("cmake", "--build", PLAY, "--target", "disruptor", stdout=subprocess.DEVNULL, env=tool_env())
    if not (ROOT / "input" / EXE_NAME).is_file() or not (ROOT / "disc/Disruptor.bin").is_file():
        raise RuntimeError("The local disc and extracted program are needed to verify the recipe")


# ------------------------------------------------------------------ artwork
def artwork():
    # Original geometric art, generated locally; no extracted game artwork.
    icon = Image.new("RGB", (256, 256), "#0c1118")
    draw = ImageDraw.Draw(icon)
    for i in range(5):
        x, y = 30 + i * 15, 30 + i * 15
        e = 226 - i * 15
        c = (30 + i * 15, 90 + i * 35, 100 + i * 29)
        draw.line([(x, e), (x, y), (e - 25, y), (e, y + 25), (e, e), (x, e)], fill=c, width=7)
    icon.save(BUILD / "disruptor.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    image = Image.new("RGB", (328, 628), "#0c1118")
    draw = ImageDraw.Draw(image)
    for i in range(8):
        x = 30 + i * 12
        y = 185 + i * 18
        e = 298 - i * 12
        bottom = 463 - i * 14
        c = (25 + i * 7, 50 + i * 23, 60 + i * 21)
        draw.line([(x, bottom), (x, y), (e - 27, y), (e, y + 27), (e, bottom), (x, bottom)], fill=c, width=3)
    fontdir = Path(os.environ["WINDIR"]) / "Fonts"
    bold = ImageFont.truetype(str(fontdir / "segoeuib.ttf"), 33)
    normal = ImageFont.truetype(str(fontdir / "segoeui.ttf"), 18)
    draw.rectangle((28, 40, 77, 44), fill="#5be8da")
    draw.text((25, 66), "DISRUPTOR", font=bold, fill="#ecf4f7")
    draw.text((29, 112), "R E C O M P I L E D", font=normal, fill="#5be8da")
    draw.text((29, 545), "WINDOWS EDITION", font=normal, fill="#98adb9")
    image.save(BUILD / "wizard.bmp")
    icon.resize((116, 116), Image.Resampling.LANCZOS).save(BUILD / "wizard-small.bmp")


# ------------------------------------------------------------------ player executables
def resource(name: str, description: str, filename: str) -> Path:
    v = META["version"]
    wv = META["windows_version"].replace(".", ",")
    rc = BUILD / f"{name}.rc"
    rc.write_text(f'''#include <windows.h>
1 ICON "disruptor.ico"
1 RT_MANIFEST "../../release/launcher.manifest"
1 VERSIONINFO
FILEVERSION {wv}
PRODUCTVERSION {wv}
FILEFLAGSMASK 0x3fL
FILEFLAGS 0x2L
FILEOS VOS_NT_WINDOWS32
FILETYPE VFT_APP
BEGIN
 BLOCK "StringFileInfo"
 BEGIN
  BLOCK "040904b0"
  BEGIN
   VALUE "FileDescription", "{description}\\0"
   VALUE "FileVersion", "{v}\\0"
   VALUE "ProductName", "Disruptor Recompiled\\0"
   VALUE "ProductVersion", "{v}\\0"
   VALUE "OriginalFilename", "{filename}\\0"
  END
 END
 BLOCK "VarFileInfo"
 BEGIN
  VALUE "Translation", 0x409, 1200
 END
END
''')
    res = BUILD / f"{name}.res"
    run("windres", rc.name, "-O", "coff", "-o", res.name, cwd=BUILD, env=tool_env())
    return res


def executables():
    (BUILD / "release_config.h").write_text(
        f'#define RELEASE_VERSION_W L"{META["version"]}"\n'
        f'#define RELEASE_VERSION "{META["version"]}"\n'
        f'#define DISC_SIZE {META["disc_size"]}ULL\n'
        f'#define DISC_SHA256 "{META["disc_sha256"]}"\n')
    common = ["g++", "-std=c++17", "-O2", "-s", "-Wall", "-Wextra", "-Wno-missing-field-initializers",
              "-municode", "-static", "-static-libgcc", "-static-libstdc++", "-I", BUILD, "-I", ROOT / "release"]
    run(*common, "-mwindows", ROOT / "release/launcher.cpp", resource("launcher", "Disruptor Recompiled Launcher", "DisruptorLauncher.exe"),
        "-o", STAGE / "DisruptorLauncher.exe", "-lbcrypt", "-lshell32", "-lgdi32", "-lole32", "-ldwmapi", "-luuid",
        "-lcomctl32", "-lshlwapi", env=tool_env())
    run(*common, "-mconsole", ROOT / "release/builder.cpp", resource("builder", "Disruptor Recompiled Builder", "DisruptorBuilder.exe"),
        "-o", STAGE / "DisruptorBuilder.exe", "-lbcrypt", "-lshell32", "-lole32", "-luuid", env=tool_env())


# ------------------------------------------------------------------ recompiler
def static_recompiler() -> Path:
    """The recompiler, linked statically so it needs no MinGW DLLs on the player's PC."""
    out = BUILD / "recompiler"
    # Installation paths can contain non-ASCII characters (a Windows user name, for
    # example); with this manifest its UTF-8 paths and narrow file calls agree.
    (BUILD / "recompiler.rc").write_text('1 24 "../../release/recompiler.manifest"\n')
    run("windres", "recompiler.rc", "-O", "coff", "-o", "recompiler-manifest.o", cwd=BUILD, env=tool_env())
    manifest = (BUILD / "recompiler-manifest.o").as_posix()
    run("cmake", "-S", ROOT / "psxrecomp/recompiler", "-B", out, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_C_COMPILER=gcc", "-DCMAKE_CXX_COMPILER=g++", "-DPSXRECOMP_ENABLE_CHD=OFF",
        f"-DCMAKE_EXE_LINKER_FLAGS=-static -static-libgcc -static-libstdc++ {manifest}",
        stdout=subprocess.DEVNULL, env=tool_env())
    run("cmake", "--build", out, "--target", "psxrecomp-game", "--parallel", str(os.cpu_count() or 4),
        stdout=subprocess.DEVNULL, env=tool_env())
    exe = out / "psxrecomp-game.exe"
    header = (ROOT / "psxrecomp/runtime/include/overlay_codegen_hash.h").read_text()
    expected = re.search(r"0x([0-9a-fA-F]{8})", header).group(1).lower()
    actual = output(exe, "--codegen-hash").strip().lower().removeprefix("0x")
    if actual != expected:
        raise RuntimeError(f"Recompiler codegen hash {actual} != runtime {expected}")
    return exe


# ------------------------------------------------------------------ disc, program, seeds
def iso_extract(disc: Path, iso_name: str) -> bytes:
    """Mirror of extractExecutable() in builder.cpp (raw MODE2/2352, Form 1 user data)."""
    with disc.open("rb") as f:
        def sector(lba):
            f.seek(lba * 2352 + 24)
            return f.read(2048)

        def read(lba, size):
            out = b""
            while len(out) < size:
                out += sector(lba + len(out) // 2048)
            return out[:size]

        pvd = sector(16)
        assert pvd[1:6] == b"CD001"
        root_lba = int.from_bytes(pvd[158:162], "little")
        root_size = int.from_bytes(pvd[166:170], "little")
        d = read(root_lba, root_size)
        for base in range(0, len(d), 2048):
            at = base
            while at < base + 2048 and d[at]:
                length = d[at]
                name = d[at + 33:at + 33 + d[at + 32]].decode("ascii", "replace")
                if name.upper() == iso_name.upper():
                    return read(int.from_bytes(d[at + 2:at + 6], "little"), int.from_bytes(d[at + 10:at + 14], "little"))
                at += length
    raise RuntimeError(f"{iso_name} not found on the disc")


def render_seeds(exe: bytes, extra: bytes) -> bytes:
    """Mirror of writeSeeds() in builder.cpp (probe_disc.py's JAL scan + extra seeds)."""
    pc0, load, size = (int.from_bytes(exe[o:o + 4], "little") for o in (0x10, 0x18, 0x1C))
    text = exe[0x800:0x800 + size]
    found = {pc0 & ~3}
    for off in range(0, len(text) - 3, 4):
        w = int.from_bytes(text[off:off + 4], "little")
        if w >> 26 != 3:
            continue
        target = ((load + off) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
        if load <= target < load + len(text) and target & 3 == 0:
            found.add(target)
    # probe_disc.py writes its part in text mode (CRLF on Windows); build.ps1 then
    # appends the extra seeds file as-is plus a CRLF.
    out = (f"# Auto-scanned JAL targets (+ entry) from {EXE_NAME}\r\n"
           f"# entry=0x{pc0:08x} load=0x{load:08x} text_size=0x{size:x}\r\n"
           "# First-pass only \u2014 add overlay / runtime discoveries as you decomp.\r\n").encode()
    out += "".join(f"0x{a:08X}\r\n" for a in sorted(found)).encode()
    return out + extra + b"\r\n"


def program_recipe() -> dict:
    exe = (ROOT / "input" / EXE_NAME).read_bytes()
    iso_name = EXE_NAME + ";1"
    if iso_extract(ROOT / "disc/Disruptor.bin", iso_name) != exe:
        raise RuntimeError("Disc extraction does not reproduce input/" + EXE_NAME)
    extra = (ROOT / "seeds/functions_extra.txt").read_bytes()
    seeds = render_seeds(exe, extra)
    if seeds != (ROOT / "input/functions.txt").read_bytes():
        raise RuntimeError("The seed scan does not reproduce input/functions.txt; rerun build.ps1")
    copy("seeds/functions_extra.txt", "kit/seeds/functions_extra.txt")
    return {"exe": {"iso_name": iso_name, "file": EXE_NAME, "sha256": sha_bytes(exe)},
            "seeds": {"extra": "seeds/functions_extra.txt", "sha256": sha_bytes(seeds)}}


def translation_recipe(recompiler: Path) -> dict:
    """Regenerates the C in isolation with the release recompiler; it must equal what build-play compiled."""
    work = BUILD / "regen"
    (work / "input").mkdir(parents=True)
    (work / "psxrecomp/bios").mkdir(parents=True)
    # Anchor the recompiler's upward project-root search here, not at this repository.
    (work / ".gitignore").write_text("*\n")
    shutil.copy2(ROOT / "game.toml", work / "game.toml")
    shutil.copy2(ROOT / "input" / EXE_NAME, work / "input" / EXE_NAME)
    shutil.copy2(ROOT / "input/functions.txt", work / "input/functions.txt")
    shutil.copy2(ROOT / "psxrecomp/bios/OpenBIOS.toml", work / "psxrecomp/bios/OpenBIOS.toml")
    run(recompiler, "--config", "game.toml", cwd=work, stdout=subprocess.DEVNULL)
    generated = {}
    for file in sorted((work / "generated").iterdir()):
        tested = ROOT / "generated" / file.name
        if not tested.is_file() or tested.read_bytes() != file.read_bytes():
            raise RuntimeError(f"Regenerated {file.name} differs from the tested build")
        generated[file.name] = digest(file)
    return {"generated": generated}


# ------------------------------------------------------------------ compile + link
def compile_recipe(ninja: Ninja) -> dict:
    """Per-unit flags as CMake passed them (the dispatch table is built without the
    fast-timing header), with the repository include paths mapped into the kit."""
    stmts = ninja.find(lambda b: b["outputs"][0].startswith("CMakeFiles/disruptor.dir/generated/" + EXE_NAME))
    if len(stmts) < 2:
        raise RuntimeError("No generated game objects in build-play/build.ninja")
    copy("src/disruptor_fast_timing.h", "kit/src/disruptor_fast_timing.h")
    profiles, units = {}, []
    for b in sorted(stmts, key=lambda b: b["outputs"][0]):
        v = b["vars"]
        args, tokens = win_split(v["DEFINES"]), win_split(v["FLAGS"])
        for tok in win_split(v["INCLUDES"]):
            if Path(tok[2:]).resolve() == (ROOT / "psxrecomp/runtime/include").resolve():
                args.append("-I@KIT/psxrecomp/runtime/include")
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "-include":
                if Path(tokens[i + 1]).resolve() != (ROOT / "src/disruptor_fast_timing.h").resolve():
                    raise RuntimeError("Unexpected forced include for generated units")
                args += ["-include", "@KIT/src/disruptor_fast_timing.h"]
                i += 2
                continue
            if tok.startswith("-I") and Path(tok[2:]).resolve() == (ROOT / "generated").resolve():
                args.append("-I@WORK/generated")
                i += 1
                continue
            args.append(tok)
            i += 1
        key = json.dumps(args)
        profiles.setdefault(key, {"name": f"p{len(profiles)}", "args": args})
        obj = play_path(b["outputs"][0])
        units.append({"source": Path(b["inputs"][0]).name, "object": obj.name, "sha256": digest(obj),
                      "profile": profiles[key]["name"]})
    return {"profiles": {p["name"]: p["args"] for p in profiles.values()}, "units": units}


def link_recipe(ninja: Ninja) -> tuple[dict, list[str]]:
    (stmt,) = ninja.find(lambda b: b["outputs"][0] == "DisruptorRecompiled.exe")
    v = stmt["vars"]
    inputs, verify_inputs = [], []
    for index, item in enumerate(stmt["inputs"]):
        path = play_path(item)
        if "/generated/" + EXE_NAME in path.as_posix():
            inputs.append("@" + path.name)
        else:
            dest = f"runtime/obj/{index:03d}_{path.name}"
            copy(path, "kit/" + dest)
            inputs.append(dest)
        verify_inputs.append(path)
    libs, verify_libs, seen = [], [], set()
    for tok in win_split(v["LINK_LIBRARIES"]):
        if tok.startswith("-"):
            libs.append(tok)
            verify_libs.append(tok)
            continue
        path = play_path(tok)
        name = path.name
        if name in seen:
            raise RuntimeError(f"Duplicate library name {name}")
        seen.add(name)
        copy(path, "kit/runtime/lib/" + name)
        libs.append("runtime/lib/" + name)
        verify_libs.append(str(KIT / "runtime/lib" / name))
    args = win_split(v["FLAGS"]) + win_split(v["LINK_FLAGS"])
    expected = normalized_pe_sha(PLAY / "DisruptorRecompiled.exe")
    # Link once from the staged runtime (plus the tested game objects) to prove the kit
    # reproduces the tested executable, and record what the linker opens.
    rsp = BUILD / "verify-link.rsp"
    staged = [KIT / i if not i.startswith("@") else p for i, p in zip(inputs, verify_inputs)]
    rsp.write_text("\n".join('"%s"' % str(p).replace("\\", "/") for p in staged) + "\n" +
                   "\n".join(x if x.startswith("-") else '"%s"' % x.replace("\\", "/") for x in verify_libs) + "\n")
    out = BUILD / "verify.exe"
    trace = output("g++", *args, "@" + str(rsp), "-o", out, "-Wl,--trace", env=tool_env())
    if normalized_pe_sha(out) != expected:
        raise RuntimeError("Linking the staged runtime does not reproduce the tested executable")
    return {"args": args, "inputs": inputs, "libs": libs, "normalized_sha256": expected}, trace.splitlines()


# ------------------------------------------------------------------ kernel code
def compile_overlays_module():
    spec = importlib.util.spec_from_file_location("compile_overlays", ROOT / "psxrecomp/tools/compile_overlays.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kernel_recipe(recompiler: Path) -> tuple[dict, list[str], list[str]]:
    overlays = compile_overlays_module()
    include = str(ROOT / "psxrecomp/runtime/include")
    overlays.verify_recompiler_matches_tag(str(recompiler), overlays.codegen_hash(include))
    tag = overlays.cache_tag(include, str(recompiler), str(ROOT / "game.toml"), flavor=KERNEL_FLAVOR)
    rel = Path("SLUS-00224/gcc/win-x64") / tag
    tested = ROOT / "build/cache" / rel
    modules = sorted(p.name for p in tested.glob("*.dll"))
    if not modules:
        raise RuntimeError("No current PGXP kernel cache; run warm_cache.ps1")
    openbios = (ROOT / "psxrecomp/bios/openbios.bin").read_bytes()
    finals = {}
    for rec in json.loads((ROOT / "build" / TESTED_CAPTURES[0]).read_text()):
        finals[rec["load_addr"]] = base64.b64decode(rec["bytes_b64"])
    captures, pages = [], {}
    for name in TESTED_CAPTURES:
        records = json.loads((ROOT / "build" / name).read_text(encoding="utf-8"))
        # The builder writes json.dumps' layout (the tested files mix layouts; only
        # the content matters to compile_overlays.py), so fingerprint that form.
        canonical = json.dumps(records)
        out = []
        for rec in records:
            data = base64.b64decode(rec["bytes_b64"])
            source = finals[rec["load_addr"]]
            pages[crc_hex(source)] = rec["load_addr"]
            diffs = [i for i in range(0, len(data), 4) if data[i:i + 4] != source[i:i + 4]]
            restore = []
            if diffs:
                start, end = diffs[0], diffs[-1] + 4
                span = data[start:end]
                at = openbios.find(span)
                if at < 0 or openbios.find(span, at + 1) >= 0:
                    raise RuntimeError(f"{name}: the pre-patch bytes are not a unique OpenBIOS sequence")
                restore.append({"offset": start, "openbios_offset": at, "length": end - start})
                rebuilt = source[:start] + openbios[at:at + end - start] + source[end:]
                if rebuilt != data:
                    raise RuntimeError(f"{name}: page cannot be rebuilt from its final state and OpenBIOS")
            fields = {k: (None if k == "bytes_b64" else v) for k, v in rec.items()}
            out.append({"page": crc_hex(source), "restore": restore, "crc32": crc_hex(data), "fields": fields})
        captures.append({"file": name, "sha256": sha_bytes(canonical.encode()), "records": out})
    # Rebuild the modules the way the builder will: from these captures, with the
    # release recompiler, and Python in UTF-8 mode. (Without it Python writes the
    # framework preamble's comments in the PC's ANSI code page, so the sources and
    # their pair IDs would depend on the player's Windows language.) The result
    # must differ from the tested cache only in that comment encoding.
    root = BUILD / "regen"
    shutil.copy2(ROOT / "psxrecomp/bios/SCPH1001.toml", root / "psxrecomp/bios/SCPH1001.toml")
    reference = BUILD / "kernel-reference"
    env = tool_env()
    env["PYTHONUTF8"] = "1"
    for capture in captures:
        path = BUILD / "kernel-captures" / capture["file"]
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(json.loads((ROOT / "build" / capture["file"]).read_text(encoding="utf-8"))))
        run(sys.executable, ROOT / "psxrecomp/tools/compile_overlays.py", "--captures", path,
            "--game-toml", root / "game.toml", "--recompiler", recompiler, "--runtime-include", include,
            "--project-root", root, "--out-dir", reference, "--compiler", "gcc", "--gcc", TC / "bin/gcc.exe",
            "--flavor", str(KERNEL_FLAVOR), cwd=root, env=env, stdout=subprocess.DEVNULL)
    built = reference / rel
    if sorted(p.name for p in built.glob("*.dll")) != modules:
        raise RuntimeError("Rebuilt kernel modules differ from the tested set")
    # The tested sources mix UTF-8 (the recompiler's comments) and cp1252 (the preamble's).
    codecs.register_error("cp1252-fallback", lambda e: (e.object[e.start:e.end].decode("cp1252"), e.end))
    # The pair ID is a hash of the source text, so it follows the encoding too.
    pair = re.compile(r"(overlay_pair_id\(void\) \{\s*return UINT64_C\()0x[0-9A-Fa-f]{16}")
    for c in tested.glob("*.c"):
        before = pair.sub(r"\1X", c.read_bytes().decode("utf-8", "cp1252-fallback"))
        if before != pair.sub(r"\1X", (built / c.name).read_bytes().decode("utf-8")):
            raise RuntimeError(f"Rebuilt {c.name} differs from the tested source beyond text encoding")
    for r in tested.glob("*.ranges"):
        strip = lambda p: [l for l in p.read_text().splitlines() if not l.startswith("P ")]
        if strip(r) != strip(built / r.name):
            raise RuntimeError(f"Rebuilt {r.name} differs from the tested code ranges")
    files = {p.name: digest(p) for p in sorted(built.iterdir()) if p.suffix in (".c", ".ranges")}
    # Record the headers and libraries a kernel-module build uses.
    shard_flags = ["-shared", "-O2", "-DPSX_OVERLAY_DLL_BUILD", "-DPSX_NO_DEBUG_TOOLS", "-DPSX_ENABLE_BLOCK_CYCLES=1",
                   f"-DPSX_OVERLAY_FLAVOR={KERNEL_FLAVOR}", "-DPSX_PGXP=1", "-I", include]
    deps = []
    for c in sorted(built.glob("*.c")):
        deps += make_deps(output("gcc", *shard_flags[1:], "-M", c, env=tool_env()))
    sample = sorted(built.glob("*.c"))[0]
    trace = output("gcc", *shard_flags, sample, "-o", BUILD / "verify-shard.dll", "-lm", "-Wl,--trace", env=tool_env())
    recipe = {"pages": [{"load_addr": addr, "crc32": crc} for crc, addr in sorted(pages.items())],
              "boot_timeout_seconds": 150, "captures": captures, "cache_dir": rel.as_posix(),
              "files": files, "modules": modules}
    return recipe, deps, trace.splitlines()


def make_deps(text: str) -> list[str]:
    text = text.replace("\\\r\n", " ").replace("\\\n", " ")
    _, _, rest = text.partition(": ")
    return [t.replace("\\ ", " ") for t in re.split(r"(?<!\\)\s+", rest.strip()) if t]


def generated_header_deps(compile: dict) -> list[str]:
    def args(unit):
        # The kit's copies are identical to these repository files.
        return [a.replace("@KIT/", str(ROOT) + "/").replace("@WORK/", str(ROOT) + "/")
                for a in compile["profiles"][unit["profile"]]]
    with concurrent.futures.ThreadPoolExecutor() as pool:
        results = pool.map(lambda u: output("gcc", *args(u), "-M", ROOT / "generated" / u["source"], env=tool_env()),
                           compile["units"])
        return [d for text in results for d in make_deps(text)]


# ------------------------------------------------------------------ toolchain
def is_system_dll(name: str) -> bool:
    lower = name.lower()
    return lower.startswith(("api-ms-win-", "ext-ms-win-")) or (SYSTEM_DIR / name).is_file()


def dll_imports(path: Path) -> list[str]:
    text = output("objdump", "-p", path, env=tool_env())
    return re.findall(r"DLL Name:\s*(\S+)", text)


def dll_closure(roots: list[Path], search: list[Path]) -> set[Path]:
    """Every non-system DLL the given binaries load, resolved like Windows would (own dir, then search)."""
    seen, queue = set(), list(roots)
    while queue:
        item = queue.pop()
        if item in seen:
            continue
        seen.add(item)
        for name in dll_imports(item):
            if is_system_dll(name):
                continue
            for folder in [item.parent, *search]:
                candidate = folder / name
                if candidate.is_file():
                    queue.append(candidate)
                    break
            else:
                raise RuntimeError(f"{item.name} needs {name}, which was not found")
    return seen


def stage_toolchain(paths: list[str]):
    """A trimmed copy of the toolchain: the programs, their DLLs, and exactly the
    headers, startup objects and libraries the game and kernel builds were seen to use."""
    programs = [TC / "bin/gcc.exe", TC / "bin/g++.exe", TC / LIBEXEC / "cc1.exe", TC / LIBEXEC / "collect2.exe",
                TC / LIBEXEC / "lto-wrapper.exe", TC / LIBEXEC / "liblto_plugin.dll",
                TC / TRIPLE / "bin/as.exe", TC / TRIPLE / "bin/ld.exe"]
    files = dll_closure(programs, [TC / "bin"])
    for p in paths:
        p = p.strip()
        if not p or p.endswith((":", "/")):
            continue
        candidate = Path(os.path.normpath(p if Path(p).is_absolute() else TC / "bin" / p))
        try:
            candidate.relative_to(TC)
        except ValueError:
            continue
        if candidate.is_file():
            files.add(candidate)
    for f in sorted(files):
        copy(f, Path("kit/toolchain") / f.relative_to(TC))
    (KIT / "toolchain/VERSION.txt").write_text((TC / "version_info.txt").read_text(errors="replace"))
    return len(files)


def trace_paths(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        line = line.strip()
        # ld --trace prints the files it opens, one per line; skip diagnostics.
        if line and not line.startswith(("ld", "collect2", "COLLECT", "attempt")) and not line.endswith(":"):
            out.append(line)
    return out


# ------------------------------------------------------------------ private Python
PY_SKIP_DIRS = {"test", "tests", "idle_test", "idlelib", "tkinter", "turtledemo", "ensurepip", "site-packages",
                "venv", "lib2to3", "pydoc_data", "__pycache__", "sqlite3", "__phello__"}
PY_SKIP_EXT = ("_test", "_tkinter", "_sqlite3", "_ssl", "_hashlib", "winsound", "_remote_debugging", "xxlimited")


def stage_python():
    base = Path(sys.base_prefix)
    dest = KIT / "python"
    dest.mkdir(parents=True)
    version = f"{sys.version_info.major}{sys.version_info.minor}"
    for name in ["python.exe", f"python{version}.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"]:
        shutil.copy2(base / name, dest / name)
    for pyd in sorted((base / "DLLs").glob("*.pyd")):
        if not pyd.stem.startswith(PY_SKIP_EXT):
            shutil.copy2(pyd, dest / pyd.name)
    for dll in dll_closure(sorted(dest.glob("*.pyd")) + [dest / "python.exe"], [base / "DLLs", base]):
        if dll.parent != dest:
            shutil.copy2(dll, dest / dll.name)
    # The standard library as bytecode in one zip (compiled here: the installed
    # Python's own __pycache__ folders are not writable).
    import py_compile
    lib = base / "Lib"
    pyc_root = BUILD / "pyc"
    with zipfile.ZipFile(dest / f"python{version}.zip", "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for source in sorted(lib.rglob("*.py")):
            rel = source.relative_to(lib)
            if set(rel.parts[:-1]) & PY_SKIP_DIRS or rel.parts[0] in PY_SKIP_DIRS or rel.name == "turtle.py":
                continue
            target = pyc_root / rel.with_suffix(".pyc")
            target.parent.mkdir(parents=True, exist_ok=True)
            py_compile.compile(str(source), cfile=str(target), dfile=rel.as_posix(), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            zf.write(target, rel.with_suffix(".pyc").as_posix())
    (dest / f"python{version}._pth").write_text(f"python{version}.zip\n.\n")


# ------------------------------------------------------------------ framework files
def stage_framework(recompiler: Path):
    copy(recompiler, "kit/recompiler/psxrecomp-game.exe")
    copy("psxrecomp/tools/compile_overlays.py", "kit/psxrecomp/tools/compile_overlays.py")
    copy("psxrecomp/bios/OpenBIOS.toml", "kit/psxrecomp/bios/OpenBIOS.toml")
    # Overlay (kernel code) recompiles look for this profile under the project root.
    copy("psxrecomp/bios/SCPH1001.toml", "kit/psxrecomp/bios/SCPH1001.toml")
    for header in sorted((ROOT / "psxrecomp/runtime/include").rglob("*")):
        if header.is_file():
            copy(header, Path("kit") / header.relative_to(ROOT))


def stage_game():
    copy("game.toml", "game.toml")
    for file in ["settings.toml", "keybinds.ini"]:
        copy("config/" + file, "game/" + file)
        copy("config/" + file, "kit/defaults/" + file)  # the launcher's "restore defaults"
    copy("release/config.ini", "game/config.ini")
    for file in ["bios/openbios.bin", "bios/OpenBIOS.LICENSE", "assets/psxrecomp.png"]:
        copy(PLAY / file, "game/" + file)
    for file in (PLAY / "mods/bundled").rglob("manifest.toml"):
        copy(file, Path("game/mods/bundled") / file.relative_to(PLAY / "mods/bundled"))
    (STAGE / "disc").mkdir()
    (STAGE / "disc/Disruptor.cue").write_text('FILE "Disruptor.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    copy("release/PLAYER-README.txt", "docs/README.txt")
    sources = BUILD / "TOOLCHAIN-SOURCES.txt"
    sources.write_text(
        "SOURCE CODE OF THE BUNDLED BUILD TOOLS\n\n"
        "Setup builds the game on your PC with the tools in the kit folder. They are\n"
        "unmodified binaries of these open-source releases. The exact source archives\n"
        "are published as toolchain-source-code.zip next to each installer at\n"
        "https://github.com/Phroster/DisruptorRecomp/releases\n\n"
        f"{(TC / 'version_info.txt').read_text(errors='replace').strip()}\n\n"
        "  GCC                 https://gcc.gnu.org/ (release " + GCC_VERSION + ")\n"
        "  GNU Binutils        https://sourceware.org/binutils/\n"
        "  MinGW-w64           https://www.mingw-w64.org/\n"
        "  GMP / MPFR / MPC    https://gmplib.org/  https://www.mpfr.org/  https://www.multiprecision.org/mpc/\n"
        "  isl                 https://libisl.sourceforge.io/\n"
        "  libiconv, gettext   https://www.gnu.org/software/libiconv/  https://www.gnu.org/software/gettext/\n"
        "  zlib, zstd          https://zlib.net/  https://github.com/facebook/zstd\n"
        "  WinLibs build       https://winlibs.com/  https://github.com/brechtsanders/winlibs_mingw\n"
        f"  Python {sys.version.split()[0]:<13}https://www.python.org/downloads/source/\n")
    licenses = {
        "psxrecomp/LICENSE": "PSXRecomp.txt",
        PLAY / "bios/OpenBIOS.LICENSE": "OpenBIOS.txt",
        PLAY / "_deps/sdl3-src/LICENSE.txt": "SDL3.txt",
        PLAY / "_deps/psx_zlib-src/LICENSE": "zlib-runtime.txt",
        PLAY / "_deps/psx_libchdr-src/LICENSE.txt": "libchdr.txt",
        PLAY / "_deps/psx_libchdr-src/deps/lzma-25.01/LICENSE": "LZMA.txt",
        PLAY / "_deps/sdl3-src/src/video/yuv2rgb/LICENSE": "yuv2rgb.txt",
        PLAY / "_deps/sdl3-src/src/hidapi/LICENSE-bsd.txt": "HIDAPI-BSD.txt",
        "psxrecomp/runtime/licenses/libchdr-NOTICES.txt": "libchdr-dependencies.txt",
        "psxrecomp/runtime/licenses/stb_image-NOTICES.txt": "stb_image.txt",
        "psxrecomp/runtime/licenses/toml11-NOTICES.txt": "toml11.txt",
        "release/licenses/MinGW-w64.txt": "MinGW-w64.txt",
        "release/licenses/winpthreads.txt": "winpthreads.txt",
        "release/licenses/GCC-runtime-exception.txt": "GCC-runtime-exception.txt",
        "release/licenses/GPL-3.0.txt": "GPL-3.0.txt",
        "release/licenses/LGPL-3.0.txt": "LGPL-3.0.txt",
        "release/licenses/LGPL-2.1.txt": "LGPL-2.1.txt",
        "release/licenses/zstd.txt": "zstd.txt",
        "release/licenses/zlib.txt": "zlib.txt",
        Path(sys.base_prefix) / "LICENSE.txt": "Python.txt",
        sources: "TOOLCHAIN-SOURCES.txt",
    }
    notices = ["DISRUPTOR RECOMPILED - THIRD-PARTY NOTICES\n",
               "Unofficial, noncommercial fan project. Original game rights remain with their owners.\n"
               "This download contains no game code or game data. Setup builds the game on your PC\n"
               "from your own disc image.\n"
               "PSXRecomp: PolyForm Noncommercial License 1.0.0.\n"
               "Bundled build tools (kit/): GCC " + GCC_VERSION + " and GNU Binutils (GPL-3.0 with the GCC Runtime\n"
               "Library Exception), MinGW-w64 and winpthreads, GMP/MPFR/MPC (LGPL-3.0), isl (MIT),\n"
               "libiconv and libintl (LGPL-2.1), zlib, zstd (BSD), and Python (PSF License).\n"
               "Where to obtain their source code is described in TOOLCHAIN-SOURCES.txt.\n"
               "Component license texts follow.\n"]
    for src, name in licenses.items():
        copy(src, "docs/licenses/" + name)
        text = (Path(src) if Path(src).is_absolute() else ROOT / src).read_text(encoding="utf-8", errors="replace")
        notices.append("\n" + "=" * 70 + "\n" + name + "\n" + "=" * 70 + "\n" + text)
    (STAGE / "docs/THIRD-PARTY-NOTICES.txt").write_text("\n".join(notices), encoding="utf-8-sig")


# ------------------------------------------------------------------ audit
WINDOW = 32


def game_windows() -> set[bytes]:
    """32-byte, 4-aligned windows of the game program that are distinctive enough to
    recognise. Mostly-text windows are left out: generic strings such as a hex-digit
    table also occur in ordinary programs."""
    exe = (ROOT / "input" / EXE_NAME).read_bytes()
    windows = set()
    for i in range(0x800, len(exe) - WINDOW, 4):
        w = exe[i:i + WINDOW]
        printable = sum(32 <= c < 127 for c in w)
        if len(set(w)) >= 12 and printable < WINDOW * 3 // 4:
            windows.add(w)
    return windows


def audit(recipe: dict):
    toolchain = KIT / "toolchain"
    python = KIT / "python"
    files = []
    for file in sorted(STAGE.rglob("*")):
        if not file.is_file() or file.name == ".release-owned":
            continue
        rel = file.relative_to(STAGE).as_posix()
        if EXE_NAME.lower() in rel.lower() or file.suffix.lower() in (".bin", ".iso", ".img") and rel != "game/bios/openbios.bin":
            raise RuntimeError(f"Game data in staging: {rel}")
        if file.suffix.lower() == ".c":
            raise RuntimeError(f"Source translation in staging: {rel}")
        data = file.read_bytes().lower()
        for private in (str(ROOT), str(Path.home())):
            if private.lower().encode() in data or private.lower().encode("utf-16-le") in data:
                raise RuntimeError(f"Private build path found in {rel}")
        files.append({"path": rel, "bytes": file.stat().st_size, "sha256": digest(file)})

    # No shipped object defines a translated game function.
    load = int(re.search(r'load_address\s*=\s*"(0x[0-9A-Fa-f]+)"', (ROOT / "game.toml").read_text()).group(1), 16)
    size = int(re.search(r'text_size\s*=\s*"(0x[0-9A-Fa-f]+)"', (ROOT / "game.toml").read_text()).group(1), 16)
    for obj in sorted((KIT / "runtime").rglob("*")):
        if not obj.is_file():
            continue
        for m in re.finditer(r" [TtDdBbRr] func_([0-9A-Fa-f]{8})\b", output("nm", "--defined-only", obj, env=tool_env())):
            if load <= int(m.group(1), 16) < load + size:
                raise RuntimeError(f"{obj.name} defines translated game function func_{m.group(1)}")

    # No staged file of ours carries the game's program bytes. Third-party tools are
    # checked instead for being unmodified copies of their sources.
    windows = game_windows()
    for file in sorted(STAGE.rglob("*")):
        if not file.is_file() or toolchain in file.parents or python in file.parents:
            continue
        if file.name == "openbios.bin" and file.read_bytes() == (ROOT / "psxrecomp/bios/openbios.bin").read_bytes():
            continue
        data = file.read_bytes()
        for i in range(0, max(0, len(data) - WINDOW + 1)):
            if data[i:i + WINDOW] in windows:
                raise RuntimeError(f"Game program bytes found in {file.relative_to(STAGE)} at {i:#x}")
    for f in toolchain.rglob("*"):
        if f.is_file() and f.name != "VERSION.txt" and digest(f) != digest(TC / f.relative_to(toolchain)):
            raise RuntimeError(f"Toolchain file differs from its source: {f}")

    # Player executables must run without any MinGW runtime installed.
    for exe in [STAGE / "DisruptorLauncher.exe", STAGE / "DisruptorBuilder.exe"]:
        missing = [d for d in dll_imports(exe) if not is_system_dll(d)]
        if missing:
            raise RuntimeError(f"Unbundled dependencies in {exe.name}: {missing}")
    manifest = {"version": META["version"],
                "source_commit": output("git", "rev-parse", "HEAD").strip(),
                "framework_commit": output("git", "-C", "psxrecomp", "rev-parse", "HEAD").strip(),
                "toolchain": f"GCC {GCC_VERSION} ({TC.name})", "game_code_included": False, "disc_embedded": False,
                "files": files,
                "framework_patches": [{"name": p.name, "sha256": digest(p)} for p in sorted((ROOT / "patches").glob("*.patch"))]}
    (STAGE / "docs/package-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Audit passed: {len(files)} files, no game code or data, runtime reproduces the tested link", flush=True)


# ------------------------------------------------------------------ main
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iscc", type=Path)
    parser.add_argument("--stage-only", action="store_true", help="stop before compiling the installer")
    args = parser.parse_args()
    preflight()
    DIST.mkdir(exist_ok=True)
    reset_owned(BUILD)
    reset_owned(STAGE)
    artwork()
    recompiler = static_recompiler()
    stage_framework(recompiler)
    ninja = Ninja(PLAY / "build.ninja")
    recipe = {"version": META["version"], "toolchain": f"GCC {GCC_VERSION}",
              "disc": {"size": META["disc_size"], "sha256": META["disc_sha256"]}}
    recipe.update(program_recipe())
    recipe["recompile"] = translation_recipe(recompiler)
    recipe["compile"] = compile_recipe(ninja)
    recipe["link"], link_trace = link_recipe(ninja)
    recipe["kernel"], kernel_deps, kernel_trace = kernel_recipe(recompiler)
    count = stage_toolchain(generated_header_deps(recipe["compile"]) + kernel_deps +
                            trace_paths(link_trace) + trace_paths(kernel_trace))
    print(f"Staged {count} toolchain files", flush=True)
    stage_python()
    (KIT / "recipe.json").write_text(json.dumps(recipe, indent=1) + "\n")
    executables()
    stage_game()
    audit(recipe)
    if args.stage_only:
        return
    (BUILD / "version.iss").write_text(
        f'#define AppVersion "{META["version"]}"\n#define WindowsVersion "{META["windows_version"]}"\n'
        f'#define DiscSize {META["disc_size"]}\n#define DiscHash "{META["disc_sha256"]}"\n')
    iscc = args.iscc or Path(os.environ["LOCALAPPDATA"]) / "Programs/Inno Setup 7/ISCC.exe"
    run(iscc, "/Qp", ROOT / "release/installer.iss")
    setup = DIST / f'DisruptorRecompiled-{META["version"]}-Setup.exe'
    (DIST / "SHA256SUMS.txt").write_text(f"{digest(setup)}  {setup.name}\n")
    print(f"Built: {setup.name} ({setup.stat().st_size:,} bytes)", flush=True)


if __name__ == "__main__":
    main()
