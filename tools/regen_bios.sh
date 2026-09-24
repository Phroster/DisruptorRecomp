#!/usr/bin/env bash
set -euo pipefail
# Use the GCC distribution's DLLs instead of Git Bash's bundled MinGW DLLs.
export PATH="$(dirname "$(command -v gcc)"):$PATH"
exec bash psxrecomp/tools/regen_bios.sh --config bios/OpenBIOS.toml
