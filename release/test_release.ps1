param([string]$Disc = (Join-Path $PSScriptRoot '..\disc\Disruptor.bin'))
$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (Get-Process DisruptorRecompiled -ErrorAction SilentlyContinue) { throw 'Close the game before release verification.' }
    . .\tools\card_guard.ps1
    $Guard = Save-CardState
    python release/test_release.py --disc $Disc
    if ($LASTEXITCODE -ne 0) { throw 'Release integration checks failed. See dist/test-results.json and installer logs.' }
}
finally {
    if (Get-Variable Guard -ErrorAction SilentlyContinue) { Restore-CardState $Guard }
    Pop-Location
}
