# Headless A/B of the host cost of one engine pass in a saved view.
#   .\tools\pass_cost_run.ps1 -Dir build-fast -Overclock 300 -Slot 0
# Starts the given build uncapped and headless, loads the savestate and prints
# tools/pass_cost.py's line (passes per VBlank, guest Hz, host ms per pass),
# then the interpreter counters. Needs a build with the debug server.
param([string]$Dir = 'build', [int]$Overclock = 300, [int]$Slot = 0,
      [int]$Seconds = 8, [int]$Repeat = 2, [string]$Hold = '', [switch]$Profile, [int]$BootWait = 45,
      [switch]$HighPriority)
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
    New-Item -ItemType Directory -Force logs | Out-Null
    $env:PSX_HEADLESS = '1'
    $env:PSX_HEADLESS_INPUT = '1'
    $env:PSX_OVERLAY_AUTOCOMPILE_OFF = '1'
    $env:PSX_CPU_OVERCLOCK = "$Overclock"
    $Game = Start-Process -FilePath (Resolve-Path ".\$Dir\DisruptorRecompiled.exe") `
        -ArgumentList '--game','game.toml','--disc','disc/Disruptor.cue' `
        -RedirectStandardOutput 'logs\pass_cost.out' -RedirectStandardError 'logs\pass_cost.err' `
        -PassThru -WindowStyle Hidden
    # A hidden background process can be moved to efficiency cores while another
    # application has the foreground; -HighPriority keeps the measurement honest.
    if ($HighPriority) { $Game.PriorityClass = 'High' }
    try {
        # A savestate load requested during the first ~40 s of boot does not take.
        Start-Sleep $BootWait
        for ($i = 0; $i -lt $Repeat; $i++) {
            if ($Hold) { python tools/pass_cost.py --slot $Slot --seconds $Seconds --hold $Hold }
            else { python tools/pass_cost.py --slot $Slot --seconds $Seconds }
        }
        if ($Profile) { python tools/host_profile.py --exe "$Dir/DisruptorRecompiled.exe" --seconds 10 --top 28 }
        python -c "import sys, json; sys.path.insert(0, 'tools'); from ask import ask; d = ask(4624, json.dumps({'cmd': 'dirty_ram_stats'}), timeout=10.0, tries=2); print('interpreter since start: blocks=%d insns=%d' % (d['blocks_run'], d['insns_run']))"
    }
    finally { Stop-Process -Id $Game.Id -Force -ErrorAction SilentlyContinue; Start-Sleep 1 }
}
finally { Restore-CardState $CardGuard; Pop-Location }
