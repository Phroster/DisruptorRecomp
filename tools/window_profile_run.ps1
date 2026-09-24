# Windowed (real GL presenter) host profile of a saved view:
#   .\tools\window_profile_run.ps1 -Dir build-fast -Slot 0
# Shows how the game thread's time splits between recompiled code, runtime,
# GL driver and waiting for the next frame - the actual 60 fps headroom.
param([string]$Dir = 'build', [int]$Overclock = 300, [int]$Slot = 0, [int]$Seconds = 10)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    . .\tools\card_guard.ps1
    $CardGuard = Save-CardState
    if (!(Test-Path "$Dir/DisruptorRecompiled.exe")) { throw "No $Dir build." }
    if (Get-Process DisruptorRecompiled -ErrorAction SilentlyContinue) { throw 'Close the running game first.' }
    if ($Dir -ne 'build' -and !(Test-Path "$Dir/cache") -and (Test-Path 'build/cache')) {
        New-Item -ItemType Junction -Path "$Dir/cache" -Target (Resolve-Path 'build/cache') | Out-Null
    }
    if (!(Test-Path "$Dir/keybinds.ini")) { Copy-Item 'config/keybinds.ini' "$Dir/keybinds.ini" }
    if (!(Test-Path "$Dir/settings.toml")) {
        (Get-Content 'config/settings.toml') -replace '^fullscreen\s*=.*', 'fullscreen = 0' |
            Set-Content -Encoding utf8 "$Dir/settings.toml"
    }
    Remove-Item Env:PSX_HEADLESS, Env:PSX_HEADLESS_INPUT -ErrorAction SilentlyContinue
    $env:PSX_OVERLAY_AUTOCOMPILE_OFF = '1'
    $env:PSX_CPU_OVERCLOCK = "$Overclock"
    $Game = Start-Process -FilePath (Resolve-Path ".\$Dir\DisruptorRecompiled.exe") `
        -ArgumentList '--game','game.toml','--disc','disc/Disruptor.cue' `
        -RedirectStandardOutput 'logs\window_profile.out' -RedirectStandardError 'logs\window_profile.err' -PassThru
    try {
        Start-Sleep 12
        python tools/pass_cost.py --slot $Slot --seconds 4
        python tools/host_profile.py --exe "$Dir/DisruptorRecompiled.exe" --seconds $Seconds --top 24
    }
    finally { Stop-Process -Id $Game.Id -Force -ErrorAction SilentlyContinue; Start-Sleep 1 }
}
finally { Restore-CardState $CardGuard; Pop-Location }
