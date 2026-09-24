# Silent off-screen GL run (no window on screen, no sound, memory card guarded):
# load a savestate and count cracks between polygons (tools/seam_census.py).
#   .\tools\seam_run.ps1 -Slot 6 -Hold left
# -Env "NAME=VALUE,..." passes extra environment variables to the game.
# -Py "tools/x.py --arg 1" runs another measurement script against the loaded state.
param([string]$Dir = 'build', [int]$Slot = 6, [string]$Hold = 'left', [int]$Frames = 60,
      [string]$Env = '', [string]$Label = '', [switch]$CpuMode, [string]$Shot = '', [string]$TurnShots = '', [switch]$NoCensus, [string]$Capture = '', [string]$Py = '')
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    . .\tools\card_guard.ps1
    $CardGuard = Save-CardState
    if (Get-Process DisruptorRecompiled -ErrorAction SilentlyContinue) { throw 'Close the running game first.' }
    $Set = @()
    foreach ($Pair in ($Env -split ',' | Where-Object { $_ })) {
        $k, $v = $Pair -split '=', 2
        Set-Item "Env:$k" $v; $Set += $k
    }
    if ($CpuMode) { $env:PSX_PGXP_CPU_MODE = '1'; $Set += 'PSX_PGXP_CPU_MODE' }
    $Out = python tools/offscreen_game.py --dir $Dir
    $GamePid = [int]($Out -replace '^pid (\d+).*', '$1')
    try {
        Start-Sleep 25
        python tools/load_state.py --slot $Slot
        if ($LASTEXITCODE -ne 0) { throw 'savestate load did not apply' }
        if (!$NoCensus) { python tools/seam_census.py --frames $Frames --hold $Hold --label $Label }
        if ($Capture) { python tools/seam_coverage.py capture --frames $Frames --hold $Hold --out $Capture }
        if ($TurnShots) { python tools/turn_shots.py --prefix $TurnShots --hold $Hold --n 6 }
        if ($Py) { $PyArgs = $Py -split ' '; python @PyArgs }
        if ($Shot) { python tools/shot.py --out $Shot }
    }
    finally { Stop-Process -Id $GamePid -Force -ErrorAction SilentlyContinue; Start-Sleep 2 }
}
finally {
    foreach ($k in $Set) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
    Restore-CardState $CardGuard
    Pop-Location
}
