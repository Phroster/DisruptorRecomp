@echo off
rem Starts the game from Command Prompt, the Run box or a double-click.
rem (.ps1 files open in Notepad there; this hands run.ps1 to PowerShell.)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
