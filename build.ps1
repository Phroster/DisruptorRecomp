param([int]$Jobs = 12, [switch]$SkipGenerate, [switch]$SkipTests, [switch]$SkipPlayBuild, [switch]$AccurateTiming, [switch]$NoPgxp)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = $PSScriptRoot
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
Push-Location $ProjectRoot
try {
    foreach ($tool in @('git','python','cmake','ninja','gcc','g++')) {
        if (!(Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Missing prerequisite: $tool" }
    }
    if (!(Test-Path 'psxrecomp/runtime/runtime.cmake')) {
        Invoke-Checked git @('submodule','update','--init','psxrecomp')
    }
    foreach ($Patch in (Get-ChildItem 'patches/*.patch')) {
        $PatchPath = $Patch.FullName
        $SavedPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & git -C psxrecomp apply --reverse --check $PatchPath 2>$null
            $AlreadyApplied = $LASTEXITCODE -eq 0
        }
        finally { $ErrorActionPreference = $SavedPreference }
        if (!$AlreadyApplied) {
            Invoke-Checked git @('-C','psxrecomp','apply','--check',$PatchPath)
            Invoke-Checked git @('-C','psxrecomp','apply',$PatchPath)
        }
    }
    $RecompilerBuild = '.local/build-recompiler'
    Invoke-Checked cmake @('-S','psxrecomp/recompiler','-B',$RecompilerBuild,'-G','Ninja',
        '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER=gcc','-DCMAKE_CXX_COMPILER=g++',
        '-DPSXRECOMP_ENABLE_CHD=OFF')
    Invoke-Checked cmake @('--build',$RecompilerBuild,'--parallel',"$Jobs")
    Invoke-Checked cmake @('-P','tools/stamp_codegen.cmake')
    if (!$SkipTests) { Invoke-Checked ctest @('--test-dir',$RecompilerBuild,'--output-on-failure','--parallel',"$Jobs") }
    if (!$SkipGenerate) {
        Invoke-Checked python @('tools/prepare_disc.py')
        # prepare_disc.py regenerates input/functions.txt from disc-derived
        # seeds; re-append the runtime-discovered extras so they survive.
        if (Test-Path 'seeds/functions_extra.txt') {
            Add-Content -LiteralPath 'input/functions.txt' `
                -Value (Get-Content -LiteralPath 'seeds/functions_extra.txt' -Raw)
        }
        $GitExe = (Get-Command git).Source
        $GitRoot = Split-Path (Split-Path $GitExe -Parent) -Parent
        $Bash = Join-Path $GitRoot 'bin/bash.exe'
        if (!(Test-Path -LiteralPath $Bash)) { throw 'Git for Windows Bash is required to regenerate OpenBIOS.' }
        $PreviousBuild = $env:PSXRECOMP_BIOS_BUILD
        $env:PSXRECOMP_BIOS_BUILD = '../.local/build-recompiler'
        try {
            # Git Bash otherwise puts its older MinGW DLLs before our compiler's DLLs.
            Invoke-Checked $Bash @('tools/regen_bios.sh')
        }
        finally { $env:PSXRECOMP_BIOS_BUILD = $PreviousBuild }
        Invoke-Checked (Join-Path $ProjectRoot "$RecompilerBuild/psxrecomp-game.exe") @('--config','game.toml')
    }
    # Fast guest timing for the recompiled game code (src/disruptor_fast_timing.h):
    # measured 11.3 -> 6.8 ms of host CPU per engine pass in the heaviest saved
    # view. -AccurateTiming builds the framework's cycle-accurate model instead.
    $Timing = if ($AccurateTiming) { '-DDISRUPTOR_FAST_TIMING=0' } else { '-DDISRUPTOR_FAST_TIMING=5' }
    # PGXP precision engine (sub-pixel vertices, perspective-correct textures;
    # switched on by game.toml [video]). -NoPgxp builds without its hooks.
    $Pgxp = if ($NoPgxp) { '-DDISRUPTOR_PGXP=OFF' } else { '-DDISRUPTOR_PGXP=ON' }
    Invoke-Checked cmake @('-S','.','-B','build','-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_C_COMPILER=gcc','-DCMAKE_CXX_COMPILER=g++',$Timing,$Pgxp)
    Invoke-Checked cmake @('--build','build','--target','disruptor','--parallel',"$Jobs")
    # Lean play build: same sources with the debug tooling compiled out. The
    # diagnostics build above calls into the debug server at every basic block
    # and function entry (~20-25 % of the game thread); run.ps1 plays this one.
    if (!$SkipPlayBuild) {
        Invoke-Checked cmake @('-S','.','-B','build-play','-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_C_COMPILER=gcc','-DCMAKE_CXX_COMPILER=g++','-DPSX_DEBUG_TOOLS=OFF',$Timing,$Pgxp)
        Invoke-Checked cmake @('--build','build-play','--target','disruptor','--parallel',"$Jobs")
    }
    Write-Host 'Build complete: build-play/ (play) and build/ (diagnostics). Launch with .\run.ps1.'
    # The native shard cache is keyed by a hash of game.toml and the code
    # generator: after changing either, the old shards are ignored and the
    # kernel code interprets until the cache is rebuilt.
    Write-Host 'If game.toml or the recompiler changed (or this is a fresh clone), run .\warm_cache.ps1 next.' -ForegroundColor Yellow
}
finally { Pop-Location }
