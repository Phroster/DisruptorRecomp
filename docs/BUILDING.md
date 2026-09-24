# Building and developing Disruptor Recompiled

This page is for people who want to build the project from source, work on it,
or understand how it is put together. Players only need the installer from the
[Releases page](https://github.com/Phroster/DisruptorRecomp/releases); see the
[README](../README.md).

How the player installer is made and how it builds the game on a player's PC is
described in [release/README.md](../release/README.md).

## What the project changes

| Feature | What it does |
|---|---|
| Native Windows build | Runs as a regular 64-bit Windows program. No emulator, no BIOS file. |
| Precompiled game code | The game executable and observed boot-time kernel code are compiled ahead of time. Measured startup and tested gameplay use zero interpreter instructions; unseen runtime code retains a fallback. |
| True 60 fps | The engine originally drew 30 frames per second. A small patch set makes it draw all 60, while game speed stays exactly like the original. |
| True 16:9 | The portal, frustum, terrain, sprite and sky clip tests are widened, so the wide view shows real geometry, objects and the continuing sky panorama. Menus stay 4:3. |
| Mouse look | Mouse movement drives the view every frame, finer than the engine's own 1.4 degree steps. Sensitivity is adjustable. |
| PC controls | Keyboard and mouse (WASD layout), remappable in `keybinds.ini`; the mouse wheel scrolls weapons and psionic powers. Controllers work too. |
| Smooth presentation | Flip-model presentation paced at an even 60 Hz; G-SYNC/FreeSync engage in borderless fullscreen. |
| 4x internal resolution | The 320x240 game renders at 1280x960 on the GPU. |
| Stable geometry (PGXP) | Sub-pixel vertex positions and perspective-correct texturing: no polygon wobble, no texture warping. |
| Steady sprites | Bodies, pickups and enemies are projected by the game's CPU code in whole pixels; their exact positions and sizes are carried through that arithmetic, so they stay put on the ground while the view moves. |
| Watertight meshes | A renderer-side crack fill closes the hairline gaps that the game's meshes show at high resolution. |
| Smart texture filtering | Consistent bilinear on terrain; smoother shading and chunky, crisp shapes on sprites, HUD and text. |
| Larger, smoother movies | Videos fit the screen at their original proportions with bicubic smoothing. Only empty padding is removed; the full picture stays visible. |
| Seamless terrain | Texture and lighting are blended across the borders between neighbouring terrain quads. |
| Savestates | **F7** opens the savestate menu. |
| Headless mode + debug server | Optional, for automated testing and measurement (`tools/`). |

## Requirements for building from source

- Windows 10 1903 or newer, or Windows 11, 64-bit
- [Git for Windows](https://git-scm.com/download/win)
- Python 3.11 or newer
- CMake 3.20 or newer
- Ninja
- MinGW-w64 GCC/G++

All of `git`, `python`, `cmake`, `ninja`, `gcc` and `g++` must be available in
PowerShell.

## Build and play (step by step)

1. Install the requirements above.
2. Open PowerShell and clone the project:

   ```powershell
   git clone --recurse-submodules https://github.com/Phroster/DisruptorRecomp.git
   cd DisruptorRecomp
   ```

3. Put your disc files in a folder called `disc`, inside the project:

   ```
   DisruptorRecomp\disc\Disruptor.bin
   DisruptorRecomp\disc\Disruptor.cue
   ```

   Keep the file names exactly like that, and keep the original `MODE2/2352`
   dump. Do not convert it to a cooked ISO.

4. Build. The first build takes a while: it translates the game and OpenBIOS,
   runs the recompiler tests, and compiles everything.

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\build.ps1
   ```

5. Warm the native code cache (once per fresh clone, about two minutes, no
   window). The BIOS call gates and the exception-handler words the game
   patches into kernel RAM at boot do not exist at translation time; this
   step captures them from a headless boot and compiles them, so nothing is
   left to the runtime's fallback interpreter. It ends with a verification
   line; the target is `interpreter blocks=0 insns=0`.

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\warm_cache.ps1
   ```

6. Play:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\run.ps1
   ```

Later rebuilds after a successful generation can be faster with:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1 -SkipGenerate -SkipTests
```

The build produces two executables from the same sources:
`build-play\DisruptorRecompiled.exe`, the lean one `run.ps1` plays, and
`build\DisruptorRecompiled.exe`, a diagnostics build with a local debug port
that the scripts in `tools\` measure against (`run.ps1 -Diag` starts it). The
diagnostics hooks cost about a quarter of the game thread, so play on the lean
build. Re-run `warm_cache.ps1` after any change to `game.toml`: the native
code cache is keyed by a hash of it. The build checks your disc's hashes and
refuses any other revision.

Both builds compile the recompiled game code with fast guest timing
(`src/disruptor_fast_timing.h`, force-included in front of the generated
files, which stay untouched). The framework brackets every recompiled
instruction with a cycle-accurate timing model and runs a full interrupt check
at every branch; with the guest CPU overclocked that accuracy buys this game
nothing and was most of the host cost. Measured in the heaviest saved view:
11.3 ms of host CPU per engine pass before, 6.8 ms after. Devices, the BIOS
and the kernel code keep the accurate model. `build.ps1 -AccurateTiming`
builds without it.

## Graphics enhancements

All of these work on the host render path; the game's own state is untouched.

`game.toml` `[video]` (can be overridden per player in `settings.toml` next to
the executable, same keys):

- `supersampling = 4` - internal resolution multiplier (1..4).
- `geometry_correction = true` - sub-pixel vertex positions (PGXP).
- `perspective_texturing = true` - depth-correct texture mapping.
- `pgxp_cpu_mode = true`, `pgxp_tolerance = -1.0` - precision also follows the
  game's own vertex arithmetic; the framework's 0.5 px safety clamp is off.

Renderer switches set by the launcher (environment variables, see `run.ps1`;
set one to `0` before `run.cmd` to turn it off):

- `PSX_GL_CRACK_FILL` / `PSX_GL_CRACK_FILL_NEAR` - rim width (native pixels)
  used to close gaps between polygons, for distant and for near geometry.
- `PSX_GL_SMART_FILTER=1` - filter by what is drawn: bilinear on world geometry,
  sky and true-colour images, edge-directed scaling with smooth nearby shades
  and crisp silhouettes on sprites, HUD and text.
- `PSX_GL_FMV_FILTER=bicubic` - smooth video reconstruction, independent of
  gameplay antialiasing. Also accepts `bilinear`, `sharp` and `nearest`.
- `PSX_GL_FMV_CONTENT=320x180` - fit the complete encoded movie instead of
  its padded 320x240 canvas. All movies on the supported disc are 320x180;
  a 16:9 screen fills naturally, with bars on other shapes of screen.
  Set this to `0` to keep the original padded presentation.
- `PSX_GL_TILE_BLEND=1.0` - width in texels over which a terrain quad blends
  into its neighbour (`0.5` = plain bilinear across the border, larger = softer).

The precision engine needs the PGXP build, which `build.ps1` makes by default
(`-NoPgxp` builds without it). It pauses itself while nothing 3D is on screen;
`DISRUPTOR_PGXP_AUTOPAUSE=0` keeps it running always.

## Controls and settings

- `keybinds.ini` is created next to the executable on first run. Edit it to
  change keyboard and mouse bindings.
- Weapons: the mouse wheel scrolls the game's weapon list (down = next, up =
  previous) and selects a moment after the last notch. Psionic powers: hold
  **R** (the psionic list) and scroll. The game's own way works too: hold **Q**
  (weapons) or **R** (psionics), step with **W**/**S**, release to select; a
  quick double tap swaps to the previous weapon or power.
  `DISRUPTOR_WHEEL_SELECT=0` gives the wheel back to `keybinds.ini`.
- `DISRUPTOR_MOUSE_SENS` — mouse sensitivity, default `0.30`.
- `DISRUPTOR_INTERP_FPS` — optional frame blending (off by default). Set a
  presentation rate such as `120`, or `0` for the monitor's refresh rate.
  Blending cross-fades frames and turns vsync off; the true 60 fps engine
  looks smoother without it.
- `DISRUPTOR_INTERP_BLEND` — smoothing blend mode, `0` = linear.
- `DISRUPTOR_CPU_OVERCLOCK` — guest CPU speed in percent, default `300`.
  At 60 fps the engine gets one VBlank of guest CPU per frame; a view that
  needs more drops to 30 fps for that frame. The heaviest view measured so far
  needs between 225 and 250. Accepted range 100-400; anything else is
  ignored and the game runs at 100.
- `DISRUPTOR_SMOOTH_YAW` — `0` turns off sub-step mouse look (the engine's
  view angle is one byte, 1.4 degrees per step; the mod feeds the fractional
  angle to the engine's trig tables and camera matrix).
- `DISRUPTOR_REFRESH_HZ` — for displays without G-SYNC/FreeSync: `120` or `60`
  switches the desktop refresh rate while the game runs.
- `settings.toml` next to the executable: fullscreen mode and vsync. The
  default is borderless fullscreen with immediate presents through a DXGI
  flip-model swapchain, which is what lets G-SYNC engage.
- **F7** opens the savestate menu. The measurement tools in `tools/` can load
  a saved state to examine that exact view.

Set an environment variable before launching, for example:

```powershell
$env:DISRUPTOR_MOUSE_SENS = "0.4"
.\run.ps1
```

## Supported disc

| Item | Expected value |
|---|---|
| Region / executable | USA / `SLUS_002.24` |
| BIN size | 636,350,064 bytes |
| BIN SHA-256 | `3b49f9874e30c613ca9d17720716764cd76d0ac968c0acd0f53159366c0cf3a4` |
| EXE SHA-256 | `48e8c3143b7f5de10340c9d4a9bac8cb7e97c15eda7a0897d3cf337ad96cb2c4` |

## What is verified

- 100% of the game's code is translated to native C. The only unbuilt bytes are
  data: strings, tables and padding.
- No interpreter use since process start, checked by `warm_cache.ps1`; every
  statically visible control transfer lands on a native entry
  (`tools/static_entry_audit.py`).
- 60 fps with correct game speed and every frame a new picture in the heaviest
  measured views; audio without underruns.
- Still to verify: a full playthrough, menus, movies, cutscenes and the
  remaining levels.

## How it works (short version)

PSXRecomp translates the game's MIPS instructions into C, and those files are
compiled into a Windows executable. The framework runtime handles the PS1
hardware (graphics, audio, CD, controllers). Small patches in `patches/`, the
project's mod source in `src/` and the mod package in `mods/` add the features
above. `game.toml` records the build-time 60 fps and widescreen patches and all
build settings. Gameplay-proven extra function seeds live in `seeds/`, so rebuilds
reproduce the same 100% code coverage.
