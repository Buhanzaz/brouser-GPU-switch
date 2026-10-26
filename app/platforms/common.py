"""Small cross-platform helpers shared by the platform backends.

Everything here is standard library only and safe to import on any OS.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

log = logging.getLogger("browser_gpu_switch.common")

# Avoid a flashing console window when a GUI build shells out on Windows.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a short, read-only command execution."""

    ok: bool
    code: int
    stdout: str
    stderr: str
    error: str = ""


def run_command(
    argv: Sequence[str],
    timeout: float = 12.0,
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[str] = None,
) -> CommandResult:
    """Run argv and capture UTF-8 output.  Never raises.

    Used only for optional diagnostics (lspci, nvidia-smi, ...) and launching
    helpers; the core detection code uses the registry, sysfs and /proc
    directly.
    """
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=dict(env) if env is not None else None,
            cwd=cwd,
            creationflags=_CREATE_NO_WINDOW,
        )
        return CommandResult(
            ok=completed.returncode == 0,
            code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    except FileNotFoundError:
        return CommandResult(ok=False, code=-1, stdout="", stderr="", error="command not found")
    except subprocess.TimeoutExpired:
        return CommandResult(ok=False, code=-1, stdout="", stderr="", error="timeout")
    except OSError as exc:
        return CommandResult(ok=False, code=-1, stdout="", stderr="", error=str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("run_command failed for %r", argv, exc_info=True)
        return CommandResult(ok=False, code=-1, stdout="", stderr="", error=str(exc))


def which(name: str) -> Optional[str]:
    """Return an absolute path for an executable name, or None."""
    try:
        found = shutil.which(name)
    except Exception:
        return None
    if not found:
        return None
    try:
        if os.path.isfile(found):
            return os.path.abspath(found)
    except OSError:
        pass
    return found


def first_existing(paths: Sequence[Path | str]) -> Optional[Path]:
    """Return the first path that exists as a file, or None."""
    for candidate in paths:
        try:
            path = Path(candidate).expanduser()
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def read_text(path: Path | str, default: str = "") -> str:
    """Read a UTF-8 text file; return default on any failure."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return default


def read_lines(path: Path | str) -> List[str]:
    """Read a text file as a list of lines; return [] on failure."""
    return read_text(path).splitlines()


def expand_env(path: str) -> str:
    """Expand %VAR% / $VAR in a path, returning it unchanged on error."""
    try:
        return os.path.expandvars(os.path.expanduser(path))
    except Exception:
        return path
