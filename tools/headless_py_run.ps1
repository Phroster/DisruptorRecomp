# Headless, silent run of the diagnostics build with a savestate loaded, then
# one measurement script against it (memory card guarded):
#   .\tools\headless_py_run.ps1 -Slot 0 -Py "tools/x.py --arg 1"
# -Env "NAME=VALUE,..." passes extra environment variables to the game.
param([string]$Dir = 'build', [int]$Slot = 0, [string]$Py = '', [string]$Env = '',
      [int]$Overclock = 300, [int]$BootWait = 45)
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    . .\tools\card_guard.ps1
    $CardGuard = Save-CardState
    if (!(Test-Path "$Dir/DisruptorRecompiled.exe")) { throw "No $Dir build." }
    if (Get-Process DisruptorRecompiled -ErrorAction SilentlyContinue) { throw 'Close the running game first.' }
    New-Item -ItemType Directory -Force logs | Out-Null
    $Set = @('PSX_HEADLESS', 'PSX_HEADLESS_INPUT', 'PSX_OVERLAY_AUTOCOMPILE_OFF', 'PSX_CPU_OVERCLOCK')
    $env:PSX_HEADLESS = '1'
    $env:PSX_HEADLESS_INPUT = '1'
    $env:PSX_OVERLAY_AUTOCOMPILE_OFF = '1'
    $env:PSX_CPU_OVERCLOCK = "$Overclock"
    foreach ($Pair in ($Env -split ',' | Where-Object { $_ })) {
        $k, $v = $Pair -split '=', 2
        Set-Item "Env:$k" $v; $Set += $k
    }
    $Game = Start-Process -FilePath (Resolve-Path ".\$Dir\DisruptorRecompiled.exe") `
        -ArgumentList '--game','game.toml','--disc','disc/Disruptor.cue' `
        -RedirectStandardOutput 'logs\headless_py.out' -RedirectStandardError 'logs\headless_py.err' `
        -PassThru -WindowStyle Hidden
    try {
        # A savestate load requested during the first ~40 s of boot does not take.
        Start-Sleep $BootWait
        python tools/load_state.py --slot $Slot
        if ($LASTEXITCODE -ne 0) { throw 'savestate load did not apply' }
        if ($Py) { $PyArgs = $Py -split ' '; python @PyArgs }
    }
    finally { Stop-Process -Id $Game.Id -Force -ErrorAction SilentlyContinue; Start-Sleep 1 }
}
finally {
    foreach ($k in $Set) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
    Restore-CardState $CardGuard
    Pop-Location
}
