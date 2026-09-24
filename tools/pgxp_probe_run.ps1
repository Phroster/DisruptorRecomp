# Headless (silent, no window) PGXP coverage / cost probe of a saved view; -Windowed uses the real GL window (needs a PGXP diagnostics
# build: cmake -B build-pgxp -DDISRUPTOR_PGXP=ON, and the _f2 shard cache).
#   .\tools\pgxp_probe_run.ps1 -Dir build-pgxp -Slot 0
param([string]$Dir = 'build-pgxp', [int]$Overclock = 300, [int]$Slot = 0, [string]$Hold = 'left', [int]$BootWait = 45, [string]$Tolerance = '', [string]$Shot = '', [switch]$Windowed)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    . .\tools\card_guard.ps1
    $CardGuard = Save-CardState
    if (Get-Process DisruptorRecompiled -ErrorAction SilentlyContinue) { throw 'Close the running game first.' }
    if ($Windowed) { Remove-Item Env:PSX_HEADLESS, Env:PSX_HEADLESS_INPUT -ErrorAction SilentlyContinue }
    else { $env:PSX_HEADLESS = '1'; $env:PSX_HEADLESS_INPUT = '1' }
    $env:PSX_OVERLAY_AUTOCOMPILE_OFF = '1'
    $env:PSX_CPU_OVERCLOCK = "$Overclock"
    $Game = Start-Process -FilePath (Resolve-Path ".\$Dir\DisruptorRecompiled.exe") `
        -ArgumentList '--game','game.toml','--disc','disc/Disruptor.cue' `
        -RedirectStandardOutput 'logs\pgxp_test.out' -RedirectStandardError 'logs\pgxp_test.err' -PassThru -WindowStyle Hidden
    try {
        Start-Sleep $BootWait
        python tools/pass_cost.py --slot $Slot --seconds 4 --hold $Hold
        if ($Tolerance -ne '') { python -c "import sys, json; sys.path.insert(0, 'tools'); from ask import ask; print(ask(4624, json.dumps({'cmd':'pgxp','tolerance':float(sys.argv[1])}), timeout=10.0, tries=2))" $Tolerance }
        python tools/pgxp_census.py
        if ($Shot -ne '') { python tools/shot.py --out $Shot }
        python tools/host_profile.py --exe "$Dir/DisruptorRecompiled.exe" --seconds 6 --top 14
    }
    finally { Stop-Process -Id $Game.Id -Force -ErrorAction SilentlyContinue; Start-Sleep 1 }
}
finally { Restore-CardState $CardGuard; Pop-Location }
