#!/usr/bin/env bash
# Builds the portable Linux archive used by the GitHub release:
#
#   dist/BrouserGPUSwitch-linux-x86_64.tar.gz
#     BrouserGPUSwitch-linux-x86_64/
#       app/                      PyInstaller folder build (binary + libraries)
#       install.sh                client-side install into ~/.local
#       uninstall.sh
#       BrouserGPUSwitch.desktop
#
# The archive is the Linux counterpart of the Windows installer: unpack it and
# run ./install.sh - no root rights, no package manager, no Python.
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m PyInstaller --noconfirm --clean packaging/gpu-switch.spec

stage="dist/BrouserGPUSwitch-linux-x86_64"
rm -rf "$stage"
mkdir -p "$stage"
cp -R dist/BrouserGPUSwitch "$stage/app"
cp packaging/linux/install.sh packaging/linux/uninstall.sh packaging/linux/BrouserGPUSwitch.desktop "$stage/"
chmod +x "$stage/install.sh" "$stage/uninstall.sh" "$stage/app/BrouserGPUSwitch"

tar -czf dist/BrouserGPUSwitch-linux-x86_64.tar.gz -C dist BrouserGPUSwitch-linux-x86_64
echo "Built dist/BrouserGPUSwitch-linux-x86_64.tar.gz"
