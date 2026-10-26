#!/usr/bin/env sh
# Launch Browser GPU Switch (Linux and other POSIX systems).
set -eu
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "Python 3 not found. Install python3 with Tkinter (python3-tk on Debian/Ubuntu)." >&2
    exit 1
fi

exec "$PYTHON" main.py "$@"
