# Plays the game. Uses the lean play build (build-play, no debug tooling) when
# it exists; -Diag forces the diagnostics build (build, TCP debug server on
# port 4624, per-block recording) that the tools/ scripts talk to.
param([switch]$Diag)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (!(Test-Path 'build/DisruptorRecompiled.exe')) { throw 'Run .\build.ps1 first.' }
    if (!(Test-Path 'disc/Disruptor.cue')) { throw 'Missing disc/Disruptor.cue.' }
    # The diagnostics build calls into the debug server at every basic block and
    # function entry of the recompiled game; measured headless that costs
    # ~20-25 % of the game thread (107 vs 132 guest Hz uncapped). Play on the
    # lean build; measure on the diagnostics one.
    $Dir = 'build'
    if (!$Diag -and (Test-Path 'build-play/DisruptorRecompiled.exe')) { $Dir = 'build-play' }
    # The runtime reads keybinds.ini next to the exe and generates the
    # framework's historical layout (arrow keys, X/S/Z/A) when it is missing.
    # Seed it with the project's WASD + mouse layout on first run.
    if (!(Test-Path "$Dir/keybinds.ini")) {
        Copy-Item 'config/keybinds.ini' "$Dir/keybinds.ini"
        Write-Host "Installed the WASD + mouse layout as $Dir\keybinds.ini"
    }
    # Same for the player settings (borderless fullscreen + immediate presents:
    # what G-SYNC and the 16:9 view need). The runtime owns the file afterwards.
    if (!(Test-Path "$Dir/settings.toml")) {
        Copy-Item 'config/settings.toml' "$Dir/settings.toml"
        Write-Host "Installed default settings as $Dir\settings.toml (fullscreen; Alt+Enter toggles)"
    }
    # Both builds share one native shard cache (warm_cache.ps1 fills build\cache).
    if ($Dir -ne 'build' -and !(Test-Path "$Dir/cache") -and (Test-Path 'build/cache')) {
        New-Item -ItemType Junction -Path "$Dir/cache" -Target (Resolve-Path 'build/cache') | Out-Null
    }
    # Overlay code is precompiled into build/cache; compiling during play spawns
    # gcc and stalls the emulation thread (measured 60-130 ms hitches). New code
    # discovered during play runs interpreted until the next offline compile.
    $env:PSX_OVERLAY_AUTOCOMPILE_OFF = '1'
    # Guest CPU overclock (runtime patch 010). The 60 fps engine mod gives the
    # engine one VBlank of guest CPU per update+render pass; a pass that needs
    # more waits for the next VBlank, i.e. that frame runs at 30 fps. Measured in
    # a saved heavy view (standing still, 680 draw commands per pass):
    # 0.50 passes per VBlank at 200 % and 225 %, 1.00 at 250 %. 300 % leaves
    # margin. Devices, audio and game speed stay on stock time. Host cost
    # (diagnostics build, uncapped, that view): 133 guest Hz at 200 %, 110 at
    # 250 %, 100 at 300 % - the engine's VBlank wait is idle-skipped
    # (game.toml "vsync-wait-skippable"), so the extra guest clock is cheap.
    # Accepted range is 100-400; other values are ignored (the game runs at 100).
    if (!$env:DISRUPTOR_CPU_OVERCLOCK) { $env:DISRUPTOR_CPU_OVERCLOCK = '300' }
    $env:PSX_CPU_OVERCLOCK = $env:DISRUPTOR_CPU_OVERCLOCK
    # Crack fill (runtime patch 015): the game's meshes are not watertight - per
    # frame ~165 vertices sit 0.1-0.7 px beside a neighbouring polygon's edge
    # (tools/seam_census.py; ~124 even on whole pixels, as the original draws
    # them). Stock resolution hides that inside a pixel; 4x with sub-pixel
    # vertices shows hairlines while the view moves. Opaque 3D triangles are
    # grown by this many native pixels so neighbours overlap. 0 turns it off.
    if (!$env:PSX_GL_CRACK_FILL) { $env:PSX_GL_CRACK_FILL = '0.45' }
    # Near/large polygons and the game's clipped corners get a wider rim, up to
    # PSX_GL_CRACK_FILL_NEAR native pixels (default 1.2): close terrain still
    # showed 1-2 px gaps with a flat 0.35.
    # Smart texture filter (runtime patch 015): bilinear on world geometry, sky
    # and true-colour images; an edge-directed (xBR-style) scaler on sprites,
    # pickups, weapon, HUD and text. 0 = plain point sampling everywhere.
    if (!$env:PSX_GL_SMART_FILTER) { $env:PSX_GL_SMART_FILTER = '1' }
    # Every movie on the supported disc is encoded at 320x180 and centred in a
    # 320x240 canvas. Fit the picture, omitting only those empty padding rows.
    # The complete image keeps its proportions; bars remain when needed.
    if (!$env:PSX_GL_FMV_CONTENT) { $env:PSX_GL_FMV_CONTENT = '320x180' }
    # Movie reconstruction is independent of gameplay AA. Bicubic smooths the
    # low-resolution video without softening the world, sprites or HUD.
    if (!$env:PSX_GL_FMV_FILTER) { $env:PSX_GL_FMV_FILTER = 'bicubic' }
    # Cross-tile blend (runtime patches 014/015): terrain is quads that each map a
    # whole 32x32 tile. Filtering ramps every texel transition except the one at
    # a quad's border, where sampling clamps - so texture and per-quad lighting
    # change on a hard line there (measured jump 10-27 per channel against 5-14
    # inside a tile, tools/quad_edge_census.py). The shader mixes in the colour
    # the neighbouring quad shows at the shared edge over this many texels
    # before the border (0.5 = plain bilinear across the border); both sides
    # meet at the same 50/50 colour. 0 = off. Needs the smart filter.
    if (!$env:PSX_GL_TILE_BLEND) { $env:PSX_GL_TILE_BLEND = '1.0' }
    # Do NOT set PSX_VBLANK_DIV here: the engine's logic is VBlank-paced, so a
    # doubled VBlank rate doubles game speed (measured, rejected). See
    # patches/007 for the opt-in divider used only for render-rate diagnostics.
    # Opt-in fixed-refresh switch for panels without G-SYNC; see display_refresh.ps1.
    . .\display_refresh.ps1
    $RefreshSwitched = Enter-GameRefresh
    Write-Host "Starting $Dir\DisruptorRecompiled.exe"
    # Settings inherited from the launching terminal change how the game
    # presents (PSX_GL_DXGI=0 turns the G-SYNC capable presenter off, for
    # example), so show them, and keep the game's own log for diagnosis.
    $Inherited = Get-ChildItem Env: | Where-Object { $_.Name -match '^(PSX_|DISRUPTOR_|SDL_)' }
    $Inherited | ForEach-Object { Write-Host "  env $($_.Name)=$($_.Value)" }
    New-Item -ItemType Directory -Force logs | Out-Null
    $Inherited | ForEach-Object { "$($_.Name)=$($_.Value)" } | Set-Content -Encoding utf8 'logs\run-last.env'
    $Game = Start-Process -FilePath (Resolve-Path ".\$Dir\DisruptorRecompiled.exe") `
        -ArgumentList '--game','game.toml','--disc','disc/Disruptor.cue' -NoNewWindow -PassThru `
        -RedirectStandardOutput 'logs\run-last.log' -RedirectStandardError 'logs\run-last.err'
    # One busy thread has to finish every frame inside 16.7 ms; keep the
    # scheduler from parking it behind background work.
    try { $Game.PriorityClass = 'High' } catch {}
    $Game.WaitForExit()
    $RunExit = $Game.ExitCode
}
finally {
    if ($RefreshSwitched) { Exit-GameRefresh }
    Pop-Location
}
exit $RunExit
