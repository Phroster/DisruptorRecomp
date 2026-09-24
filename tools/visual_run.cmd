@echo off
rem Visual launcher: HLE boot (BIOS skip), full config, window + audio.
rem Usage: tools\visual_run.cmd [logfile]
setlocal
cd /d "%~dp0.."
set PSX_BIOS_HLE=1
set PSX_OVERLAY_AUTOCOMPILE_OFF=1
rem PSX_VBLANK_DIV not set: engine logic is VBlank-paced (patches/007 is diagnostic only)
if "%~1"=="" (set LOG=logs\visual.out) else (set LOG=%~1)
".\build\DisruptorRecompiled.exe" --game game.toml --disc disc/Disruptor.cue > "%LOG%" 2>&1
endlocal
