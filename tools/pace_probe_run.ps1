# Runs the game for -Seconds with the display-refresh helper active and prints
# present pacing: interval histogram, skipped guest frames, swap blocking time.
# Usage: .\tools\pace_probe_run.ps1 [-Seconds 35]   (honours DISRUPTOR_REFRESH_HZ,
#        PSX_VSYNC and the other run.ps1 environment switches)
param([int]$Seconds = 35, [string]$Log = 'logs\pace_probe.out')
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    Get-Process DisruptorRecompiled -ErrorAction SilentlyContinue | Stop-Process -Force
    $env:PSX_OVERLAY_AUTOCOMPILE_OFF = '1'
    if (!$env:DISRUPTOR_CPU_OVERCLOCK) { $env:DISRUPTOR_CPU_OVERCLOCK = '300' }
    $env:PSX_CPU_OVERCLOCK = $env:DISRUPTOR_CPU_OVERCLOCK
    . .\display_refresh.ps1
    $Switched = Enter-GameRefresh
    try {
        $Game = Start-Process -FilePath (Resolve-Path '.\build\DisruptorRecompiled.exe') `
            -ArgumentList '--game','game.toml','--disc','disc/Disruptor.cue' `
            -RedirectStandardOutput $Log -RedirectStandardError "$Log.err" -PassThru
        Start-Sleep $Seconds
        python tools/pace_report.py
        Stop-Process -Id $Game.Id -Force
    }
    finally { if ($Switched) { Exit-GameRefresh } }
    Select-String -Path $Log -Pattern 'sync-to-host|present cadence|host panel' |
        ForEach-Object { $_.Line } | Select-Object -First 6
}
finally { Pop-Location }
