# Headless check of the PGXP auto-pause (src/disruptor_widescreen.c): intro
# speed (uncapped guest Hz) and the engine's state in the intro and in a saved
# gameplay view, with the auto-pause off and on.
param([string]$Dir = 'build', [int]$Slot = 0)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    . .\tools\card_guard.ps1
    $CardGuard = Save-CardState
    if (Get-Process DisruptorRecompiled -ErrorAction SilentlyContinue) { throw 'Close the running game first.' }
    $env:PSX_HEADLESS = '1'
    $env:PSX_HEADLESS_INPUT = '1'
    $env:PSX_OVERLAY_AUTOCOMPILE_OFF = '1'
    $env:PSX_CPU_OVERCLOCK = '300'
    foreach ($AutoPause in '0', '1') {
        $env:DISRUPTOR_PGXP_AUTOPAUSE = $AutoPause
        Write-Host "=== autopause=$AutoPause"
        $Game = Start-Process -FilePath (Resolve-Path ".\$Dir\DisruptorRecompiled.exe") `
            -ArgumentList '--game','game.toml','--disc','disc/Disruptor.cue' `
            -RedirectStandardOutput 'logs\autopause.out' -RedirectStandardError 'logs\autopause.err' `
            -PassThru -WindowStyle Hidden
        try {
            Start-Sleep 8
            python tools/pgxp_autopause_probe.py intro
            Start-Sleep 22
            python tools/pass_cost.py --slot $Slot --seconds 6 --hold left
            python tools/pgxp_autopause_probe.py state
        }
        finally { Stop-Process -Id $Game.Id -Force -ErrorAction SilentlyContinue; Start-Sleep 1 }
    }
}
finally {
    $env:DISRUPTOR_PGXP_AUTOPAUSE = $null
    Restore-CardState $CardGuard
    Pop-Location
}
