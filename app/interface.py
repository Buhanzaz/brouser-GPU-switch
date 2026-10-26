"""Shared contract for Browser GPU Switch.

This module is the only shared dependency between the platform backends
(app.platforms.windows / app.platforms.linux), the Tkinter UI (app.ui) and the
tests.  It must stay dependency-free and importable on every operating system
(no winreg / ctypes.windll imports here).

Contracts
---------
* Public read methods (os_info, list_gpus, list_browsers, list_options,
  current_option) must never raise.  On failure they return an empty list or
  a safe fallback and record the problem in diagnostics().
* apply() and restore_all() / restore_browser() report problems via
  ApplyResult and do not raise either.
* Apply/restore are synchronous and should finish in well under two seconds.
* Changes are per-user only (HKCU on Windows, ~/.local on Linux).  The
  application never requires administrator / root rights.
* A backend instance may be created once per process and is used from the Tk
  main thread only.
* Backends persist their undo information through app.state.StateStore.
  They must only touch entries whose "platform" field equals their own
  platform_key.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol, Tuple

APP_NAME = "GPU Switch"
APP_VERSION = "1.0.0"

WINDOWS = "windows"
LINUX = "linux"
MOCK = "mock"

# ---------------------------------------------------------------------------
# Stable option ids.  These strings are persisted in state.json and asserted
# by tests, so never rename them.
# ---------------------------------------------------------------------------
WINDOWS_OPTION_DEFAULT = "windows:default"
WINDOWS_OPTION_POWER_SAVING = "windows:power-saving"
WINDOWS_OPTION_HIGH_PERFORMANCE = "windows:high-performance"

LINUX_OPTION_DEFAULT = "linux:default"
LINUX_OPTION_NVIDIA_OFFLOAD = "linux:nvidia-offload"
LINUX_OPTION_DRI_PRIME = "linux:dri-prime"

MOCK_OPTION_DEFAULT = "mock:default"
MOCK_OPTION_POWER_SAVING = "mock:power-saving"
MOCK_OPTION_HIGH_PERFORMANCE = "mock:high-performance"

# Windows keeps the per-application GPU preference in this HKCU key.  The value
# name is the full path of the application executable and the value data looks
# like "GpuPreference=2;" (extra fields may be present and must be preserved).
WINDOWS_GPU_PREFS_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"

# GpuPreference values used inside WINDOWS_GPU_PREFS_KEY.
WINDOWS_PREF_DEFAULT = 0
WINDOWS_PREF_POWER_SAVING = 1
WINDOWS_PREF_HIGH_PERFORMANCE = 2


class UnsupportedPlatformError(RuntimeError):
    """Raised when no backend exists for the current operating system."""


class BackendError(RuntimeError):
    """Generic backend failure (used rarely; most failures use ApplyResult)."""


def now_iso() -> str:
    """Return the current local time as ISO-8601 with an offset."""
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class OsInfo:
    """Basic information about the machine the backend runs on."""

    platform_key: str
    name: str
    version: str
    arch: str
    hostname: str
    session: str = ""

    @property
    def pretty(self) -> str:
        parts = [self.name]
        for extra in (self.version, self.arch, self.session):
            if extra:
                parts.append(extra)
        return " | ".join(parts)


@dataclass(frozen=True)
class Gpu:
    """One graphics adapter found on the machine.

    vendor is one of nvidia, amd, intel, microsoft, virtual or other.
    kind is one of discrete, integrated, virtual or unknown.
    """

    id: str
    name: str
    vendor: str
    kind: str
    driver: str = ""
    memory_mb: int = 0
    pci_address: str = ""
    detail: str = ""


@dataclass(frozen=True)
class Browser:
    """A browser that can be launched and configured.

    id must stay stable between refreshes and be unique on the machine.
    launch_command is the argv used to start the browser; when empty the
    backend falls back to executable.  process_names contains process
    basenames used for the "is it running?" check (backends may compute this
    lazily and leave the tuple empty).
    """

    id: str
    name: str
    executable: str
    launch_command: Tuple[str, ...] = ()
    engine: str = "other"
    version: str = ""
    package: str = ""
    desktop_file: str = ""
    process_names: Tuple[str, ...] = ()
    source: str = ""
    supported: bool = True
    note: str = ""

    @property
    def command(self) -> Tuple[str, ...]:
        if self.launch_command:
            return self.launch_command
        return (self.executable,) if self.executable else ()


@dataclass
class GpuOption:
    """A user-selectable GPU mode for one browser.

    The UI treats id as opaque but passes the exact object it received from
    list_options() back into apply().  kind is informational: auto,
    integrated, discrete or specific.
    payload is backend-private data (for example the environment variables a
    Linux launch needs).
    """

    id: str
    label: str
    description: str = ""
    kind: str = "auto"
    gpu_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PendingChange:
    """A change that is currently applied and can be undone."""

    key: str
    platform: str
    browser_id: str
    browser_name: str
    option_id: str
    option_label: str
    applied_at: str
    description: str


@dataclass
class ApplyResult:
    """Outcome of an apply/restore operation."""

    ok: bool
    message: str
    details: str = ""
    warnings: List[str] = field(default_factory=list)

    @classmethod
    def success(
        cls,
        message: str,
        details: str = "",
        warnings: List[str] | None = None,
    ) -> "ApplyResult":
        return cls(ok=True, message=message, details=details, warnings=list(warnings or []))

    @classmethod
    def failure(cls, message: str, details: str = "") -> "ApplyResult":
        return cls(ok=False, message=message, details=details)


@dataclass
class LaunchResult:
    """Outcome of starting a browser process."""

    ok: bool
    message: str
    pid: int = 0


class PlatformBackend(Protocol):
    """Everything the UI and the tests are allowed to call.

    Concrete implementations: app.platforms.windows.WindowsBackend,
    app.platforms.linux.LinuxBackend and app.platforms.mock.MockBackend.
    """

    platform_key: str

    def os_info(self) -> OsInfo:
        """Return OS name/version/arch.  Never raises."""

    def list_gpus(self) -> List[Gpu]:
        """Return every graphics adapter, integrated first.  Never raises."""

    def list_browsers(self) -> List[Browser]:
        """Return installed, launchable browsers sorted for display.  Never raises."""

    def list_options(self) -> List[GpuOption]:
        """Return selectable GPU modes for this machine.  Never raises.

        The list always contains the default/automatic option.  The returned
        objects are the ones that will be passed to apply().
        """

    def current_option(self, browser: Browser) -> GpuOption:
        """Return the option currently configured for the browser.

        Returns the default option when nothing was configured.  The returned
        object must have the same id as one of list_options().  Never raises.
        """

    def notes(self) -> List[str]:
        """Short, user-facing hints about platform limitations.  Never raises."""

    def is_browser_running(self, browser: Browser) -> bool:
        """True when at least one process of the browser is running.  Never raises."""

    def running_pids(self, browser: Browser) -> List[int]:
        """PIDs belonging to the browser (empty when it is not running).  Never raises."""

    def apply(self, browser: Browser, option: GpuOption) -> ApplyResult:
        """Persist the selected GPU mode for the browser.

        Must refuse (ok=False with a clear Russian message) when the browser is
        still running.  Applying twice without an intermediate restore must
        keep the original system value for the undo record.
        """

    def pending_changes(self) -> List[PendingChange]:
        """Changes applied earlier (also across application restarts).  Never raises."""

    def restore_all(self) -> ApplyResult:
        """Undo every change applied on this machine by this platform.  Never raises."""

    def restore_browser(self, browser: Browser) -> ApplyResult:
        """Undo the change applied to the browser only.  Never raises."""

    def launch(self, browser: Browser) -> LaunchResult:
        """Start the browser detached from this process.  Never raises."""

    def diagnostics(self) -> str:
        """Multi-line technical report used by main.py --diagnostics."""

    def close(self) -> None:
        """Release resources (no-op is fine)."""
