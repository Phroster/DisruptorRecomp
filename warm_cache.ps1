# Builds the native shard cache (build/cache) for the code a static recompile
# cannot see: the BIOS call gates at 0xA0/0xB0/0xC0 and the exception-handler
# words the game's own Psy-Q patchers write into kernel RAM at boot. Without
# these shards that code runs in the dirty-RAM interpreter. The cache is local
# (never committed), so run this once after build.ps1 on a fresh clone.
#
# It boots the game headless twice: once to capture the kernel code (including
# the half-second boot state between the two kernel patches), then again to
# verify that nothing is interpreted any more.
param([int]$Seconds = 30)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    . .\tools\card_guard.ps1
    $CardGuard = Save-CardState
    if (!(Test-Path 'build/DisruptorRecompiled.exe')) { throw 'Run .\build.ps1 first.' }
    if (Get-Process DisruptorRecompiled -ErrorAction SilentlyContinue) { throw 'Close the running game first.' }
    New-Item -ItemType Directory -Force logs | Out-Null
    $env:PSX_HEADLESS = '1'
    $env:PSX_HEADLESS_INPUT = '1'
    $env:PSX_OVERLAY_AUTOCOMPILE_OFF = '1'
    if (!$env:DISRUPTOR_CPU_OVERCLOCK) { $env:DISRUPTOR_CPU_OVERCLOCK = '300' }
    $env:PSX_CPU_OVERCLOCK = $env:DISRUPTOR_CPU_OVERCLOCK

    function Start-Headless([string]$Log) {
        Start-Process -FilePath (Resolve-Path '.\build\DisruptorRecompiled.exe') `
            -ArgumentList '--game','game.toml','--disc','disc/Disruptor.cue' `
            -RedirectStandardOutput $Log -RedirectStandardError "$Log.err" `
            -PassThru -WindowStyle Hidden
    }
    # PGXP builds (CMake DISRUPTOR_PGXP=ON, the default) load shards of overlay
    # flavor 2, plain builds flavor 0. Both are compiled so either build finds
    # its cache.
    function Invoke-Compile([string]$Captures) {
        foreach ($Flavor in 0, 2) {
            python 'psxrecomp/tools/compile_overlays.py' --captures $Captures --game-toml 'game.toml' `
                --recompiler '.local/build-recompiler/psxrecomp-game.exe' `
                --runtime-include 'psxrecomp/runtime/include' --project-root '.' `
                --out-dir 'build/cache' --compiler gcc --flavor $Flavor | Select-Object -Last 5
            if ($LASTEXITCODE -ne 0) { throw "compile_overlays.py failed for $Captures (flavor $Flavor)" }
        }
    }

    Write-Host 'Pass 1: capturing kernel code from a cold boot...'
    $Game = Start-Headless 'logs\warm_capture.out'
    try {
        python tools/capture_boot_window.py --out build/overlay_captures_boot.json
        $BootCaptured = $LASTEXITCODE -eq 0
        # Boot installs the kernel stubs without menu input. Blind Start/Cross
        # presses can confirm New Game and write to the player's memory card.
        python tools/interp_census.py $Seconds
        python tools/capture_kernel_gates.py
        if ($LASTEXITCODE -ne 0) { throw 'Could not capture the live kernel call gates.' }
        python -c "import sys, json; sys.path.insert(0, 'tools'); from ask import ask; print(ask(4624, json.dumps({'cmd': 'overlay_capture_dump'}), timeout=30.0, tries=2))"
    }
    finally { Stop-Process -Id $Game.Id -Force -ErrorAction SilentlyContinue; Start-Sleep 1 }

    Invoke-Compile 'build/overlay_captures.json'
    Invoke-Compile 'build/overlay_captures_gates.json'
    if ($BootCaptured) { Invoke-Compile 'build/overlay_captures_boot.json' }

    Write-Host 'Pass 2: verifying (target: interpreter +0 blocks / +0 insns)...'
    $Game = Start-Headless 'logs\warm_verify.out'
    try {
        Start-Sleep 12
        python tools/interp_census.py $Seconds
        python -c "import sys, json; sys.path.insert(0, 'tools'); from ask import ask; d = ask(4624, json.dumps({'cmd': 'dirty_ram_stats'}), timeout=10.0, tries=2); print('since process start: interpreter blocks=%d insns=%d' % (d['blocks_run'], d['insns_run'])); sys.exit(0 if d['insns_run'] == 0 else 2)"
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Some code still interprets; run warm_cache.ps1 again (captures are additive).' }
        else { Write-Host 'Cache warm: no interpreter use since process start.' -ForegroundColor Green }
    }
    finally { Stop-Process -Id $Game.Id -Force -ErrorAction SilentlyContinue }
}
finally { Restore-CardState $CardGuard; Pop-Location }
