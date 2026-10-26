r"""Persistent state and undo backups for Browser GPU Switch.

The state file is a small JSON document kept in the per-user configuration
directory (%APPDATA%\BrowserGpuSwitch on Windows,
~/.config/browser-gpu-switch on Linux).  Backends store one entry per browser
they modified; the UI reads the entries to render the "restore everything"
button, and the backends use them to undo changes even after an application
restart.

Set the environment variable BROWSER_GPU_SWITCH_HOME to redirect all data
(used by the automated tests).
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("browser_gpu_switch.state")

ENV_DATA_DIR = "BROWSER_GPU_SWITCH_HOME"
APP_DIR_NAME = "BrowserGpuSwitch"
UNIX_DIR_NAME = "browser-gpu-switch"


def default_data_dir() -> Path:
    """Return the per-user data directory for the application."""
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return Path(override).expanduser()

    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / "AppData" / "Roaming" / APP_DIR_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME

    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / UNIX_DIR_NAME


class StateStore:
    """Thread-safe JSON store with deterministic per-entry backup folders.

    Layout::

        <data_dir>/state.json
        <data_dir>/backups/<sha1(key)[:12]>/<filename>

    The store never deletes backups implicitly; backends remove them with
    remove_backup_dir() after a successful restore.
    """

    VERSION = 1

    def __init__(self, data_dir: Optional[Path | str] = None) -> None:
        self.data_dir = Path(data_dir).expanduser() if data_dir else default_data_dir()
        self.state_file = self.data_dir / "state.json"
        self.backups_dir = self.data_dir / "backups"
        self._lock = threading.RLock()
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.writable = True
        except OSError as exc:
            # Expected in restricted environments (sandbox, read-only profile).
            # Do not dump a traceback: the UI/self-test explains the situation.
            self.writable = False
            log.warning("cannot create data directory %s: %s", self.data_dir, exc)

    # -- low level ---------------------------------------------------------
    def _empty(self) -> Dict[str, Any]:
        return {"version": self.VERSION, "entries": {}}

    def _read(self) -> Dict[str, Any]:
        try:
            with self.state_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return self._empty()
        except (OSError, ValueError):
            log.warning("state file is unreadable, starting fresh", exc_info=True)
            self._quarantine()
            return self._empty()

        if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
            log.warning("state file has unexpected structure, starting fresh")
            self._quarantine()
            return self._empty()
        data.setdefault("version", self.VERSION)
        return data

    def _quarantine(self) -> None:
        """Move a corrupt state file aside instead of losing it silently."""
        try:
            if self.state_file.exists():
                target = self.state_file.with_name(
                    "state.json.corrupt-" + time.strftime("%Y%m%d-%H%M%S")
                )
                os.replace(self.state_file, target)
        except OSError:
            log.warning("could not quarantine corrupt state file", exc_info=True)

    def _write(self, data: Dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temp = self.state_file.with_name(
            ".state-" + str(os.getpid()) + "-" + str(time.time_ns()) + ".tmp"
        )
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.state_file)
        finally:
            try:
                temp.unlink()
            except OSError:
                pass

    # -- public API --------------------------------------------------------
    def load(self) -> Dict[str, Any]:
        """Return the whole state document (a defensive copy)."""
        with self._lock:
            return copy.deepcopy(self._read())

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._read()["entries"].get(key)
            return copy.deepcopy(entry) if isinstance(entry, dict) else None

    def put(self, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            data = self._read()
            data["entries"][key] = copy.deepcopy(value)
            self._write(data)

    def update(self, key: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Merge fields into the entry key and return the result."""
        with self._lock:
            data = self._read()
            entry = data["entries"].get(key)
            merged: Dict[str, Any] = dict(entry) if isinstance(entry, dict) else {}
            merged.update(copy.deepcopy(fields))
            data["entries"][key] = merged
            self._write(data)
            return copy.deepcopy(merged)

    def delete(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._read()
            entry = data["entries"].pop(key, None)
            self._write(data)
            return copy.deepcopy(entry) if isinstance(entry, dict) else None

    def keys(self) -> List[str]:
        with self._lock:
            return sorted(self._read()["entries"].keys())

    def items(self) -> List[Tuple[str, Dict[str, Any]]]:
        with self._lock:
            entries = self._read()["entries"]
            return [
                (key, copy.deepcopy(value))
                for key, value in entries.items()
                if isinstance(value, dict)
            ]

    def __len__(self) -> int:
        return len(self.keys())

    # -- backups -----------------------------------------------------------
    def _backup_dir(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        return self.backups_dir / digest

    def backup_dir(self, key: str) -> Path:
        """Return (and create) the backup folder dedicated to key."""
        folder = self._backup_dir(key)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def backup_file(self, key: str, filename: str) -> Path:
        """Return a safe path inside the backup folder for key.

        The caller decides how to fill the file (copy, write, ...).
        """
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(filename)).strip("._") or "backup"
        return self.backup_dir(key) / safe

    def remove_backup_dir(self, key: str) -> None:
        with self._lock:
            shutil.rmtree(self._backup_dir(key), ignore_errors=True)
