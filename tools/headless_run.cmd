@echo off
rem Headless test launcher: no window, no host keyboard capture, optional
rem host-input sampling so keybind/mouse pseudo-inputs can be exercised.
rem Usage: tools\headless_run.cmd [logfile]
setlocal
cd /d "%~dp0.."
set PSX_HEADLESS=1
set PSX_HEADLESS_INPUT=1
set PSX_BIOS_HLE=1
if "%~1"=="" (set LOG=logs\headless.out) else (set LOG=%~1)
".\build\DisruptorRecompiled.exe" --game game.toml --disc disc/Disruptor.cue > "%LOG%" 2>&1
endlocal
