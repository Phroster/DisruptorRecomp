# Building a release

The player deliverable is one Windows installer EXE that contains **no game code
and no game data**. It installs:

- `DisruptorLauncher.exe`: native launcher with Play, all player settings and a
  key/mouse rebinding page.
- `DisruptorBuilder.exe`: builds the game on the player's PC (`builder.cpp`).
- `kit/`: the prebuilt framework runtime objects and libraries (PSXRecomp, OpenBIOS
  translation, SDL3 and the project's own `src/` code), the recompiler, a trimmed
  copy of the project's GCC toolchain, a private Python for the framework's
  kernel-code compiler, and `recipe.json`.
- `game/`: runtime configuration, OpenBIOS, mod manifests and default settings.

Setup verifies and copies the player's disc image, then runs the builder, which:

1. extracts `SLUS_002.24` from the raw image and checks its SHA-256;
2. writes the function seeds (the same JAL scan `prepare_disc.py` uses, plus
   `seeds/functions_extra.txt`);
3. runs the recompiler with the project's `game.toml` (all recompiler patches)
   and checks every generated file against the tested build;
4. compiles the generated C with the tested flags and checks every object;
5. links it with the prebuilt runtime (which carries the framework patches in
   `patches/` and the project's mods) and checks the executable;
6. boots the new game once, hidden and silent, until the runtime's capture store
   holds the kernel pages the tested cache was compiled from; rebuilds the
   boot-window page from the final page plus the OpenBIOS prologue it replaced;
   compiles all kernel modules with `compile_overlays.py`; checks their sources;
7. deletes the extracted program, generated C and objects, and writes
   `game/build-stamp.json`.

Any mismatch stops the build with a message, so a player either gets the tested
program or none. The whole build takes about a minute.

## Build

First build the game with `build.ps1`, warm the cache with `warm_cache.ps1`, and
complete the normal source/patch validation. Packaging uses `build-play` with
`PSX_DEBUG_TOOLS=OFF` and the PGXP kernel cache. Diagnostic builds and missing
caches are rejected. The local disc and `input/` are used only to verify the
recipe; nothing from them is staged.

Builder tools: the WinLibs GCC 15.2 UCRT toolchain on PATH (it is also the one
that gets bundled), CMake, Ninja, Python 3.11+ with Pillow, and Inno Setup 7.

```powershell
python release/build_release.py
powershell -NoProfile -ExecutionPolicy Bypass -File release/test_release.ps1
```

`--stage-only` stops before compiling the installer. `--iscc PATH` points at
Inno Setup if it is not in its default per-user location. Set the version and
accepted image in `version.json`. Output is in ignored `dist/`:

- `DisruptorRecompiled-<version>-Setup.exe` and `SHA256SUMS.txt`
- `stage/kit/recipe.json` and `stage/docs/package-manifest.json` (both in Setup)
- `test-results.json` and `test-location.txt` pointing to the isolated temporary
  test folder, outside the repository, with installation/runtime logs

`build_release.py` proves the recipe before it ships it: the static recompiler
must regenerate the tested C byte for byte, the staged runtime must link the
tested objects into the tested executable (timestamp and checksum aside), and
the kernel modules rebuilt from the tested captures must match the tested cache
except for comment text encoding. The kit is trimmed to the toolchain files the
compiles and links were traced to open.

The audit then refuses the package if any staged file carries a distinctive
32-byte run of the game program, if any staged object defines a translated game
function, if a toolchain file differs from its source, or if a private build path
appears in a file.

Notes on the player-side environment, all handled by the builder:

- The recompiler resolves `game.toml` paths against the nearest folder with
  `.gitignore`, `.git` or `CMakeLists.txt`; the builder marks its work folder.
- The release recompiler has a UTF-8 code-page manifest (`recompiler.manifest`),
  as the game has; the GCC tools use the ANSI code page, so the builder hands them
  8.3 short paths when the installation path does not fit it.
- Python runs in UTF-8 mode, so kernel sources do not depend on the player's
  Windows language.

## Integration verification

Run the PowerShell wrapper with the original game closed. It protects the
development memory card with `tools/card_guard.ps1`. Tests validate the genuine
image and reject wrong-size and wrong-hash inputs, install and build into a path
with spaces and Unicode, check the built game against the recipe, boot the
installed game headlessly with an isolated profile, exercise repair (which
rebuilds), and verify preservation of settings/saves and removal of all built
files on uninstall.

`DisruptorLauncher.exe --smoke-test <new-profile> <seconds>` never opens a game
window or audio device, refuses existing profile directories, and accepts
1–180 seconds. `--verify-only <image>` returns 0 for a matching disc and 2
otherwise. `DisruptorBuilder.exe --keep-work` keeps the work folder for diagnosis.

Installation tests may temporarily create the normal Start menu/uninstall entry.
Use a disposable VM for testing over an existing release installation. Do not run
these tests over a player's installation. Failed test folders are kept as evidence.
Local automated startup is not evidence of a full gameplay or clean-VM test.

## Private publication

Commit packaging/source changes only. Rebuild after that commit so the package
manifest identifies the exact checkpoint. Verify the repo is still private,
create the release at the checkpoint, and upload the installer, `SHA256SUMS.txt`
and `toolchain-source-code.zip` (the upstream source archives of the bundled GCC,
binutils, MinGW-w64 and libraries, required by their GPL/LGPL licenses; see
`TOOLCHAIN-SOURCES.txt`). Then download the published installer and compare its
hash. Never change repository visibility during this workflow.

The installer and launcher are currently unsigned.

License texts in `licenses/`: MinGW-w64, winpthreads, the GCC runtime exception
and GPLv3 come from the official MinGW-w64 and GCC repositories; LGPL-3.0 from
CMake's bundled copy, LGPL-2.1, zlib and zstd from Git for Windows' bundled copies.
