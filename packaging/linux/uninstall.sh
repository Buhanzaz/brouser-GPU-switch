#!/bin/sh
# Removes the installation created by install.sh.
set -eu

prefix="${PREFIX:-$HOME/.local}"
app_dir="$prefix/opt/BrouserGPUSwitch"

rm -rf "$app_dir"
rm -f "$prefix/bin/BrouserGPUSwitch"
rm -f "$prefix/share/applications/BrouserGPUSwitch.desktop"

echo "Removed GPU Switch from $app_dir"
