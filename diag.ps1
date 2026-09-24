# Starts the game with its log captured, then records a frame-pacing
# diagnostic while you play. Files land in your Downloads folder:
#   disruptor-run.log    the game's own startup/runtime log
#   disruptor-diag.json  frame timing rings sampled during play
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (!(Test-Path 'build/DisruptorRecompiled.exe')) { throw 'Run .\build.ps1 first.' }
    if (!(Test-Path 'build/keybinds.ini')) { Copy-Item 'config/keybinds.ini' 'build/keybinds.ini' }
    if (!(Test-Path 'build/settings.toml')) { Copy-Item 'config/settings.toml' 'build/settings.toml' }
    $Log  = Join-Path $HOME 'Downloads\disruptor-run.log'
    $Diag = Join-Path $HOME 'Downloads\disruptor-diag.json'
    $env:PSX_OVERLAY_AUTOCOMPILE_OFF = '1'
    # Guest CPU overclock (patch 010). The 60 fps engine mod draws every VBlank,
    # and on ~10% of frames the game's update+render needs more than one stock
    # VBlank of 33.8 MHz CPU time, so that frame is skipped (measured: 113 of
    # 1199 presents were 33 ms apart). 200% gives the frame two VBlanks of
    # CPU per VBlank; devices, audio and game speed stay stock.
    if (!$env:DISRUPTOR_CPU_OVERCLOCK) { $env:DISRUPTOR_CPU_OVERCLOCK = '300' }
    $env:PSX_CPU_OVERCLOCK = $env:DISRUPTOR_CPU_OVERCLOCK
    $env:PSX_RUNTIME_PERF_DIAG = '1'
    . .\display_refresh.ps1
    $RefreshSwitched = Enter-GameRefresh
    $Game = Start-Process -FilePath (Resolve-Path '.\build\DisruptorRecompiled.exe') `
        -ArgumentList '--game','game.toml','--disc','disc/Disruptor.cue' `
        -RedirectStandardOutput $Log -RedirectStandardError "$Log.err" -PassThru
    Write-Host "Game started (pid $($Game.Id)). Log: $Log"
    Write-Host ''
    Write-Host 'Get INTO GAMEPLAY (past the menus), then keep MOVING and TURNING.' -ForegroundColor Yellow
    Write-Host 'Recording starts in 90 seconds and runs for 45 seconds.' -ForegroundColor Yellow
    for ($i = 90; $i -gt 0; $i -= 10) { Write-Host "  $i s..."; Start-Sleep 10 }
    Write-Host 'RECORDING - keep moving.' -ForegroundColor Green
    python tools/diag_capture.py --out $Diag --seconds 45
    Write-Host ''
    Write-Host "Done. Files written: $Log and $Diag" -ForegroundColor Green
    Write-Host 'The game keeps running; close it whenever you like.'
    # The temporary display mode lasts only as long as this script does.
    if ($RefreshSwitched) { Wait-Process -Id $Game.Id -ErrorAction SilentlyContinue }
}
finally {
    if ($RefreshSwitched) { Exit-GameRefresh }
    Pop-Location
}
