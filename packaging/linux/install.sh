#!/bin/sh
# Client-side installer for the portable Linux build of GPU Switch.
# It needs no root rights: everything is put into ~/.local by default
# (override with PREFIX=/some/prefix ./install.sh).

set -eu

here=$(cd "$(dirname "$0")" && pwd)
prefix="${PREFIX:-$HOME/.local}"
app_dir="$prefix/opt/BrouserGPUSwitch"

if [ ! -x "$here/app/BrouserGPUSwitch" ]; then
    echo "app/BrouserGPUSwitch is missing: unpack the archive completely first" >&2
    exit 1
fi

mkdir -p "$app_dir" "$prefix/bin" "$prefix/share/applications"
cp -R "$here/app/." "$app_dir/"
chmod +x "$app_dir/BrouserGPUSwitch"
ln -sf "$app_dir/BrouserGPUSwitch" "$prefix/bin/BrouserGPUSwitch"

sed "s|^Exec=.*|Exec=$app_dir/BrouserGPUSwitch|" \
    "$here/BrouserGPUSwitch.desktop" > "$prefix/share/applications/BrouserGPUSwitch.desktop"

echo "Installed GPU Switch into $app_dir"
echo "Run it with: BrouserGPUSwitch   (or from the application menu)"
echo "Remove it with: $here/uninstall.sh"
