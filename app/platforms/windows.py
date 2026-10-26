r"""Windows backend for Browser GPU Switch.

Detects the installed graphics adapters and web browsers through the Windows
registry and switches the *per-application* GPU preference through

    HKCU\Software\Microsoft\DirectX\UserGpuPreferences

which is exactly the value Windows itself fills in from
"Settings -> System -> Display -> Graphics" and from the NVIDIA/AMD control
panels.  Value names are full executable paths, value data looks like
"GpuPreference=2;" (0 = let Windows decide, 1 = power saving,
2 = high performance).  Other "Key=Value;" fields in the same value must be
preserved.

Design notes
------------
* Everything here is standard library only.  winreg is imported lazily and
  guarded so the module can be byte-compiled and imported on every operating
  system (on Linux the registry simply reports "no data").
* Public methods never raise: failures are reported through ApplyResult /
  empty lists and remembered in diagnostics().
* Writes only ever touch HKCU, so no administrator rights are required.
* Undo information is kept in app.state.StateStore under the key
  "windows:<normalised exe path>".  Applying a second change without an
  intermediate restore keeps the FIRST captured original value, so "restore"
  always returns the true pre-application system state.
* Process detection uses CreateToolhelp32Snapshot + QueryFullProcessImageNameW
  because tasklist and WMI may be blocked in restricted environments (they are
  blocked in the development sandbox, while this API pair is verified to
  work).
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import re
import shlex
import socket
import subprocess
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, TypeVar

try:  # pragma: no cover - the branch depends on the host OS
    import winreg as _winreg
except ImportError:  # pragma: no cover - non-Windows hosts
    _winreg = None

try:  # pragma: no cover - ctypes.wintypes is only importable on Windows
    from ctypes import wintypes as _wintypes
except Exception:  # pragma: no cover - non-Windows hosts
    _wintypes = None

from app.interface import (
    WINDOWS,
    WINDOWS_GPU_PREFS_KEY,
    WINDOWS_OPTION_DEFAULT,
    WINDOWS_OPTION_HIGH_PERFORMANCE,
    WINDOWS_OPTION_POWER_SAVING,
    WINDOWS_PREF_DEFAULT,
    WINDOWS_PREF_HIGH_PERFORMANCE,
    WINDOWS_PREF_POWER_SAVING,
    ApplyResult,
    Browser,
    Gpu,
    GpuOption,
    LaunchResult,
    OsInfo,
    PendingChange,
    now_iso,
)
from app.state import StateStore

log = logging.getLogger("browser_gpu_switch.windows")

T = TypeVar("T")

# Registry hives understood by WindowsRegistry (plain strings keep the fake
# registries used by the tests trivial to implement).
HKLM = "HKLM"
HKCU = "HKCU"

# Graphics adapters are enumerated from the "Display" setup class.
GPU_CLASS_KEY = (
    r"SYSTEM\CurrentControlSet\Control\Class"
    r"\{4d36e968-e325-11ce-bfc1-08002be10318}"
)
DISPLAY_CLASS_NAME = "display"

# Installed browsers register themselves under these three locations.
START_MENU_INTERNET_ROOTS: Tuple[Tuple[str, str], ...] = (
    (HKLM, r"SOFTWARE\Clients\StartMenuInternet"),
    (HKLM, r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet"),
    (HKCU, r"SOFTWARE\Clients\StartMenuInternet"),
)

# Internet Explorer is deliberately not offered: the legacy DirectX preference
# mechanism targets modern Chromium/Gecko browsers, and the customer asked to
# hide IE.
IE_EXECUTABLES = frozenset({"iexplore.exe"})

# subprocess creation flags: start the browser detached from this process.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

# Options sorted by kind: integrated first, then discrete, then the rest.
_KIND_ORDER = {"integrated": 0, "discrete": 1, "virtual": 2, "unknown": 3}

# GpuPreference -> stable option id (fallback when payload is not usable).
_PREFERENCE_BY_OPTION_ID: Dict[str, int] = {
    WINDOWS_OPTION_DEFAULT: WINDOWS_PREF_DEFAULT,
    WINDOWS_OPTION_POWER_SAVING: WINDOWS_PREF_POWER_SAVING,
    WINDOWS_OPTION_HIGH_PERFORMANCE: WINDOWS_PREF_HIGH_PERFORMANCE,
}

_PREFERENCE_RE = re.compile(r"GpuPreference\s*=\s*(-?\d+)", re.IGNORECASE)
_PCI_RE = re.compile(r"(PCI\\VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4}))", re.IGNORECASE)
_EXE_RE = re.compile(r"^\"?(.+?\.(?:exe|com|bat|cmd))(?:\"|\s|$)", re.IGNORECASE)
_CLIENT_SUFFIX_RE = re.compile(r"-[0-9A-F]{8,}$", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"%[0-9A-Za-z*]")

# Well-known browsers used only when the registry lists nothing at all.
_WELL_KNOWN_BROWSERS: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
    ("Google Chrome", "chrome.exe", "chromium", (r"Google\Chrome\Application\chrome.exe",)),
    ("Microsoft Edge", "msedge.exe", "chromium", (r"Microsoft\Edge\Application\msedge.exe",)),
    ("Firefox", "firefox.exe", "gecko", (r"Mozilla Firefox\firefox.exe",)),
    (
        "Firefox Developer Edition",
        "firefox.exe",
        "gecko",
        (r"Firefox Developer Edition\firefox.exe",),
    ),
    (
        "Yandex Browser",
        "browser.exe",
        "chromium",
        (r"Yandex\YandexBrowser\Application\browser.exe",),
    ),
    (
        "Brave",
        "brave.exe",
        "chromium",
        (r"BraveSoftware\Brave-Browser\Application\brave.exe",),
    ),
    ("Opera", "opera.exe", "chromium", (r"Opera\opera.exe", r"Programs\Opera\opera.exe")),
    ("Vivaldi", "vivaldi.exe", "chromium", (r"Vivaldi\Application\vivaldi.exe",)),
    ("Chromium", "chrome.exe", "chromium", (r"Chromium\Application\chrome.exe",)),
)


# ---------------------------------------------------------------------------
# Small helpers (pure functions, easy to unit-test)
# ---------------------------------------------------------------------------
def _normcase(value: Any) -> str:
    """Normalise a Windows path/registry name for case-insensitive compare.

    Equivalent to os.path.normcase on Windows but deterministic on every OS,
    which keeps the tests stable.
    """
    return str(value or "").strip().replace("/", "\\").lower()


def _as_text(value: Any) -> str:
    """Convert a raw registry value to text without raising."""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        for encoding in ("utf-16-le", "utf-8", "latin-1"):
            try:
                text = value.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
            text = text.replace("\x00", "")
            if text:
                return text
        return ""
    if value is None:
        return ""
    return str(value)


def _coerce_int(value: Any) -> int:
    """Best-effort conversion of DWORD/QWORD/REG_BINARY data to int."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, bytes):
        raw = value[:8]
        if not raw:
            return 0
        return int.from_bytes(raw, "little", signed=False)
    if isinstance(value, str):
        text = value.strip().lower().replace(" ", "")
        if not text:
            return 0
        try:
            if text.startswith("0x"):
                return int(text, 16)
            return int(text)
        except ValueError:
            return 0
    return 0


def _split_command(command_line: str) -> List[str]:
    """Split a registry shell/open/command line into argv tokens."""
    text = str(command_line or "").strip()
    if not text:
        return []
    try:
        tokens = shlex.split(text, posix=False)
    except ValueError:
        tokens = text.split()
    cleaned: List[str] = []
    for token in tokens:
        token = token.strip()
        if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
            token = token[1:-1]
        if token:
            cleaned.append(token)
    return cleaned


def _command_executable(command_line: str) -> str:
    """Return the executable path of a shell command line (quoted or not)."""
    text = str(command_line or "").strip()
    if not text:
        return ""
    if text[0] in "\"'":
        end = text.find(text[0], 1)
        candidate = text[1:end] if end > 0 else text[1:]
    else:
        tokens = _split_command(text)
        candidate = tokens[0] if tokens else text
        if not candidate.lower().endswith((".exe", ".com", ".bat", ".cmd")):
            match = _EXE_RE.match(text)
            if match:
                candidate = match.group(1)
    candidate = candidate.strip().strip("\"'")
    try:
        candidate = os.path.expandvars(candidate)
    except Exception:  # pragma: no cover - defensive
        pass
    return candidate.strip()


def _engine_for(exe_name: str, display_name: str = "") -> str:
    """Guess the browser engine from its executable/display name."""
    haystack = (str(exe_name or "") + " " + str(display_name or "")).lower()
    rules = (
        ("firefox", "gecko"),
        ("thunderbird", "gecko"),
        ("chrome", "chromium"),
        ("chromium", "chromium"),
        ("msedge", "chromium"),
        ("brave", "chromium"),
        ("opera", "chromium"),
        ("vivaldi", "chromium"),
        ("yandex", "chromium"),
        ("browser", "chromium"),
        ("iexplore", "trident"),
        ("edge", "chromium"),
    )
    for needle, engine in rules:
        if needle in haystack:
            return engine
    return "other"


def _parse_preference(data: Any) -> Optional[int]:
    """Extract GpuPreference=N from UserGpuPreferences data."""
    match = _PREFERENCE_RE.search(_as_text(data))
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _compose_preference(data: Any, preference: int) -> str:
    """Write GpuPreference=N into data keeping every other field.

    The output uses the "Key=Value;" layout Windows itself writes, e.g.
    "GpuPreference=2;" or "AppStatus=0;GpuPreference=1;".
    """
    parts: List[str] = []
    replaced = False
    for chunk in _as_text(data).split(";"):
        piece = chunk.strip()
        if not piece:
            continue
        key = piece.split("=", 1)[0].strip().lower()
        if key == "gpupreference":
            parts.append("GpuPreference=" + str(int(preference)))
            replaced = True
        else:
            parts.append(piece)
    if not replaced:
        parts.append("GpuPreference=" + str(int(preference)))
    return ";".join(parts) + ";"


def _preference_for_option(option: GpuOption) -> Optional[int]:
    """Return the GpuPreference number of option (None when unknown)."""
    if option is None:
        return None
    payload = getattr(option, "payload", None) or {}
    raw = payload.get("preference")
    if isinstance(raw, int) and WINDOWS_PREF_DEFAULT <= raw <= WINDOWS_PREF_HIGH_PERFORMANCE:
        return raw
    return _PREFERENCE_BY_OPTION_ID.get(str(getattr(option, "id", "")))


def _slug(text: Any) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return value or "item"


def _clean_client_name(key_name: str) -> str:
    """Turn a StartMenuInternet key name into a readable name."""
    name = _CLIENT_SUFFIX_RE.sub("", str(key_name or "").strip())
    return name.replace("_", " ").strip()


def _popen_detached(command: Sequence[str]) -> int:
    """Start command detached from this process; return its PID."""
    flags = 0
    if sys.platform.startswith("win"):
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(list(command), close_fds=True, creationflags=flags)
    try:
        return int(process.pid or 0)
    except Exception:  # pragma: no cover - defensive
        return 0


# ---------------------------------------------------------------------------
# Registry access
# ---------------------------------------------------------------------------
class WindowsRegistry:
    """Fault-tolerant wrapper around the winreg module.

    The API intentionally mirrors what the tests need to fake:
    get_string, list_values, list_subkeys, set_string and delete_value.
    Reads return None / empty lists instead of raising; writes propagate
    OSError so the backend can report a friendly message.
    """

    HKLM = HKLM
    HKCU = HKCU

    def __init__(self, module: Any = None) -> None:
        self._winreg = module if module is not None else _winreg
        self._last_error = ""

    # -- state -------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._winreg is not None

    @property
    def last_error(self) -> str:
        return self._last_error

    def _record(self, exc: BaseException) -> None:
        self._last_error = f"{type(exc).__name__}: {exc}"
        log.debug("registry access problem: %s", self._last_error)

    def _hive(self, root: str) -> Any:
        if self._winreg is None:
            raise OSError("winreg is unavailable on this platform")
        key = str(root or "").upper()
        if key in ("HKLM", "HKEY_LOCAL_MACHINE"):
            return self._winreg.HKEY_LOCAL_MACHINE
        if key in ("HKCU", "HKEY_CURRENT_USER"):
            return self._winreg.HKEY_CURRENT_USER
        raise KeyError("unknown registry hive: " + str(root))

    def _open(self, root: str, path: str, access: Optional[int] = None) -> Any:
        assert self._winreg is not None
        mode = self._winreg.KEY_READ if access is None else access
        return self._winreg.OpenKey(self._hive(root), str(path), 0, mode)

    # -- reads -------------------------------------------------------------
    def get_value(self, root: str, path: str, name: str = "") -> Any:
        if self._winreg is None:
            return None
        try:
            with self._open(root, path) as key:
                value, _value_type = self._winreg.QueryValueEx(key, name)
                return value
        except FileNotFoundError:
            return None
        except OSError as exc:
            self._record(exc)
            return None
        except Exception as exc:  # pragma: no cover - defensive
            self._record(exc)
            return None

    def get_string(self, root: str, path: str, name: str = "") -> Optional[str]:
        value = self.get_value(root, path, name)
        if value is None:
            return None
        return _as_text(value)

    def list_values(self, root: str, path: str) -> List[Tuple[str, Any, int]]:
        result: List[Tuple[str, Any, int]] = []
        if self._winreg is None:
            return result
        try:
            with self._open(root, path) as key:
                try:
                    count = int(self._winreg.QueryInfoKey(key)[1])
                except Exception:
                    count = 0
                for index in range(count):
                    try:
                        name, value, value_type = self._winreg.EnumValue(key, index)
                    except OSError:
                        break
                    result.append((str(name), value, int(value_type)))
        except FileNotFoundError:
            return result
        except OSError as exc:
            self._record(exc)
        except Exception as exc:  # pragma: no cover - defensive
            self._record(exc)
        return result

    def list_subkeys(self, root: str, path: str) -> List[str]:
        result: List[str] = []
        if self._winreg is None:
            return result
        try:
            with self._open(root, path) as key:
                try:
                    count = int(self._winreg.QueryInfoKey(key)[0])
                except Exception:
                    count = 0
                for index in range(count):
                    try:
                        result.append(str(self._winreg.EnumKey(key, index)))
                    except OSError:
                        break
        except FileNotFoundError:
            return result
        except OSError as exc:
            self._record(exc)
        except Exception as exc:  # pragma: no cover - defensive
            self._record(exc)
        return result

    # -- writes ------------------------------------------------------------
    def set_string(self, root: str, path: str, name: str, data: str) -> None:
        """Create/update a REG_SZ value.  Raises OSError on failure."""
        if self._winreg is None:
            raise OSError("winreg is unavailable on this platform")
        with self._winreg.CreateKeyEx(
            self._hive(root), str(path), 0, self._winreg.KEY_SET_VALUE
        ) as key:
            self._winreg.SetValueEx(key, str(name), 0, self._winreg.REG_SZ, str(data))

    def delete_value(self, root: str, path: str, name: str) -> bool:
        """Delete a value; False when it does not exist.

        Unexpected errors (for example access denied) are propagated so the
        caller can report them.
        """
        if self._winreg is None:
            return False
        try:
            with self._open(root, path, self._winreg.KEY_SET_VALUE) as key:
                try:
                    self._winreg.DeleteValue(key, str(name))
                except FileNotFoundError:
                    return False
                return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            self._record(exc)
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self._record(exc)
            raise OSError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Process enumeration (ctypes, no tasklist / WMI)
# ---------------------------------------------------------------------------
class RunningProcess:
    """One running process as seen by the backend."""

    __slots__ = ("pid", "path", "name")

    def __init__(self, pid: int, path: str = "", name: str = "") -> None:
        self.pid = int(pid or 0)
        self.path = str(path or "")
        text = str(name or "")
        if not text and self.path:
            text = os.path.basename(self.path)
        self.name = text

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"RunningProcess(pid={self.pid}, path={self.path!r})"


def _build_process_entry_struct() -> Any:
    """Create the ctypes PROCESSENTRY32W structure (Windows only)."""
    if _wintypes is None:  # pragma: no cover - non-Windows
        return None

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", _wintypes.DWORD),
            ("cntUsage", _wintypes.DWORD),
            ("th32ProcessID", _wintypes.DWORD),
            # ULONG_PTR: 32/64 bit safe.
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", _wintypes.DWORD),
            ("cntThreads", _wintypes.DWORD),
            ("th32ParentProcessID", _wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", _wintypes.DWORD),
            ("szExeFile", _wintypes.WCHAR * 260),
        ]

    return PROCESSENTRY32W


_PROCESSENTRY32W = _build_process_entry_struct()
_KERNEL32: Any = None
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_MAX_PROCESS_PATH = 4096


def _kernel32() -> Any:
    """Return a configured kernel32 handle (cached); raises on non-Windows."""
    global _KERNEL32
    if _KERNEL32 is not None:
        return _KERNEL32
    if _wintypes is None or not hasattr(ctypes, "WinDLL"):
        raise OSError("ctypes.WinDLL is unavailable on this platform")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = _wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [_wintypes.DWORD, _wintypes.DWORD]
    kernel32.Process32FirstW.restype = _wintypes.BOOL
    kernel32.Process32FirstW.argtypes = [
        _wintypes.HANDLE,
        ctypes.POINTER(_PROCESSENTRY32W),
    ]
    kernel32.Process32NextW.restype = _wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        _wintypes.HANDLE,
        ctypes.POINTER(_PROCESSENTRY32W),
    ]
    kernel32.CloseHandle.argtypes = [_wintypes.HANDLE]
    kernel32.OpenProcess.restype = _wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [_wintypes.DWORD, _wintypes.BOOL, _wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.restype = _wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [
        _wintypes.HANDLE,
        _wintypes.DWORD,
        _wintypes.LPWSTR,
        ctypes.POINTER(_wintypes.DWORD),
    ]
    _KERNEL32 = kernel32
    return kernel32


class WindowsProcessProvider:
    """Snapshot processes with CreateToolhelp32Snapshot (never raises).

    tasklist and WMI are frequently blocked; these two kernel32 calls are the
    reliable fallback and are verified to work on the target machine.
    """

    def __init__(self) -> None:
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error

    def _record(self, exc: BaseException) -> None:
        self._last_error = f"{type(exc).__name__}: {exc}"
        log.debug("process snapshot problem: %s", self._last_error)

    # -- internal ----------------------------------------------------------
    @staticmethod
    def _query_image_path(kernel32: Any, pid: int) -> str:
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(_MAX_PROCESS_PATH)
            size = _wintypes.DWORD(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return ""
            return buffer.value or ""
        except Exception:  # pragma: no cover - defensive
            return ""
        finally:
            try:
                kernel32.CloseHandle(handle)
            except Exception:  # pragma: no cover - defensive
                pass

    def _snapshot(self) -> List[RunningProcess]:
        if _wintypes is None or not sys.platform.startswith("win"):
            return []
        try:
            kernel32 = _kernel32()
        except Exception as exc:  # pragma: no cover - non-Windows
            self._record(exc)
            return []
        handle = None
        try:
            handle = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
            if not handle or handle == _INVALID_HANDLE_VALUE:
                raise OSError("CreateToolhelp32Snapshot failed")
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            result: List[RunningProcess] = []
            more = kernel32.Process32FirstW(handle, ctypes.byref(entry))
            while more:
                pid = int(entry.th32ProcessID)
                name = str(entry.szExeFile or "")
                path = self._query_image_path(kernel32, pid) if pid else ""
                result.append(RunningProcess(pid=pid, path=path, name=name))
                more = kernel32.Process32NextW(handle, ctypes.byref(entry))
            return result
        except Exception as exc:
            self._record(exc)
            return []
        finally:
            if handle:
                try:
                    kernel32.CloseHandle(handle)
                except Exception:  # pragma: no cover - defensive
                    pass

    # -- public API --------------------------------------------------------
    def processes(self) -> List[RunningProcess]:
        """Return every visible process (full image path when accessible)."""
        return list(self._snapshot())

    def snapshot(self) -> List[RunningProcess]:
        """Alias kept for callers that expect the ctypes name."""
        return self.processes()

    def running_paths(self) -> List[str]:
        return [item.path for item in self.processes() if item.path]

    def pids(self) -> List[int]:
        return [item.pid for item in self.processes()]

    def diagnostics(self) -> str:
        processes = self.processes()
        return (
            "Process provider: ctypes CreateToolhelp32Snapshot\n"
            f"Processes visible: {len(processes)}\n"
            f"Last error: {self._last_error or 'none'}"
        )


# ---------------------------------------------------------------------------
# Small system abstraction (file checks + detached launch)
# ---------------------------------------------------------------------------
class WindowsSystem:
    """Default collaborator for OS information, file checks and launching."""

    def windows_version(self) -> Tuple[int, int, int]:
        try:
            info = sys.getwindowsversion()
            return (int(info.major), int(info.minor), int(info.build))
        except Exception:  # pragma: no cover - non-Windows
            return (0, 0, 0)

    def architecture(self) -> str:
        try:
            return str(platform.machine() or "")
        except Exception:  # pragma: no cover - defensive
            return ""

    def hostname(self) -> str:
        try:
            return str(socket.gethostname() or "")
        except Exception:  # pragma: no cover - defensive
            return ""

    def file_exists(self, path: str) -> bool:
        try:
            return bool(path) and os.path.isfile(str(path))
        except OSError:
            return False

    def launch(self, command: Sequence[str]) -> int:
        return _popen_detached(command)


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
class WindowsBackend:
    """PlatformBackend implementation for Windows 10/11 (per-user only)."""

    platform_key = WINDOWS

    def __init__(
        self,
        registry: Optional[Any] = None,
        process_provider: Optional[Any] = None,
        state: Optional[StateStore] = None,
        system: Optional[Any] = None,
    ) -> None:
        self._registry = registry if registry is not None else WindowsRegistry()
        self._processes = (
            process_provider if process_provider is not None else WindowsProcessProvider()
        )
        self._state = state if state is not None else StateStore()
        self._system = system if system is not None else WindowsSystem()
        self._errors: List[str] = []

    # -- error bookkeeping -------------------------------------------------
    def _record_error(self, operation: str, exc: BaseException) -> None:
        message = f"{operation}: {type(exc).__name__}: {exc}"
        log.warning("windows backend: %s", message)
        self._errors.append(message)
        del self._errors[:-20]

    def _guard(self, operation: str, func: Callable[[], T], fallback: Callable[[], T]) -> T:
        try:
            return func()
        except Exception as exc:
            self._record_error(operation, exc)
            return fallback()

    # -- collaborator helpers ----------------------------------------------
    def _file_exists(self, path: str) -> bool:
        if not path:
            return False
        checker = getattr(self._system, "file_exists", None)
        if callable(checker):
            try:
                return bool(checker(path))
            except Exception as exc:
                self._record_error("system.file_exists", exc)
                return False
        try:
            return os.path.isfile(os.path.expandvars(str(path)))
        except OSError:
            return False

    def _system_value(self, name: str, fallback: Callable[[], str]) -> str:
        getter = getattr(self._system, name, None)
        if callable(getter):
            try:
                value = getter()
                if value:
                    return str(value)
            except Exception as exc:
                self._record_error("system." + name, exc)
        try:
            return str(fallback() or "")
        except Exception:  # pragma: no cover - defensive
            return ""

    def _windows_version(self) -> Tuple[int, int, int]:
        getter = getattr(self._system, "windows_version", None)
        if callable(getter):
            try:
                value = getter()
                if value:
                    parts = [int(part) for part in value][:3]
                    while len(parts) < 3:
                        parts.append(0)
                    return (parts[0], parts[1], parts[2])
            except Exception as exc:
                self._record_error("system.windows_version", exc)
        try:
            info = sys.getwindowsversion()
            return (int(info.major), int(info.minor), int(info.build))
        except Exception:  # pragma: no cover - non-Windows
            return (0, 0, 0)

    def _time_now(self) -> str:
        clock = getattr(self._system, "now_iso", None)
        if callable(clock):
            try:
                value = clock()
                if value:
                    return str(value)
            except Exception:
                pass
        return now_iso()

    # -- OS information ----------------------------------------------------
    def os_info(self) -> OsInfo:
        return self._guard("os_info", self._os_info, self._fallback_os_info)

    def _fallback_os_info(self) -> OsInfo:
        return OsInfo(
            platform_key=WINDOWS,
            name="Windows",
            version="",
            arch="",
            hostname="",
        )

    def _os_info(self) -> OsInfo:
        major, minor, build = self._windows_version()
        if major >= 10 and build >= 22000:
            name = "Windows 11"
        elif major >= 10:
            name = "Windows 10"
        elif major:
            name = f"Windows {major}.{minor}"
        else:
            name = platform.system() or "Windows"
        if build:
            version = f"{major}.{minor}.{build}"
        elif major:
            version = f"{major}.{minor}"
        else:
            version = platform.release() or ""
        arch = self._system_value("architecture", platform.machine)
        hostname = self._system_value("hostname", socket.gethostname)
        session = "64-разрядная система" if sys.maxsize > 2 ** 32 else "32-разрядная система"
        return OsInfo(
            platform_key=WINDOWS,
            name=name,
            version=version,
            arch=arch,
            hostname=hostname,
            session=session,
        )

    # -- GPUs --------------------------------------------------------------
    def list_gpus(self) -> List[Gpu]:
        return self._guard("list_gpus", self._list_gpus, list)

    def _list_gpus(self) -> List[Gpu]:
        root_class = self._registry.get_string(HKLM, GPU_CLASS_KEY, "Class")
        if root_class and str(root_class).strip().lower() != DISPLAY_CLASS_NAME:
            self._record_error(
                "list_gpus",
                RuntimeError("class key is not Display: " + str(root_class)),
            )
            return []

        subkeys = self._registry.list_subkeys(HKLM, GPU_CLASS_KEY)
        numeric_subkeys = sorted(
            (name for name in subkeys if re.fullmatch(r"\d+", str(name or ""))),
            key=lambda item: int(item),
        )
        gpus: List[Gpu] = []
        used_ids: set = set()
        for subkey in numeric_subkeys:
            key_path = GPU_CLASS_KEY + "\\" + str(subkey)
            values: Dict[str, Tuple[Any, int]] = {}
            for name, value, value_type in self._registry.list_values(HKLM, key_path):
                values[str(name).lower()] = (value, int(value_type))

            class_value = _as_text(values.get("class", ("", 0))[0]).strip().lower()
            if class_value and class_value != DISPLAY_CLASS_NAME:
                continue

            description = _as_text(values.get("driverdesc", ("", 0))[0]).strip()
            if not description:
                continue
            provider = _as_text(values.get("providername", ("", 0))[0]).strip()
            matching = _as_text(values.get("matchingdeviceid", ("", 0))[0]).strip()
            driver = _as_text(values.get("driverversion", ("", 0))[0]).strip()
            vendor = _classify_vendor(provider, matching, description)
            kind = _classify_kind(vendor, description)
            memory_mb = _memory_mb(values)
            pci_address, ven, dev = _parse_pci(matching)

            if ven and dev:
                base_id = f"windows:gpu:{ven.lower()}:{dev.lower()}"
            else:
                base_id = f"windows:gpu:{subkey}"
            gpu_id = base_id
            suffix = 2
            while gpu_id in used_ids:
                gpu_id = f"{base_id}-{suffix}"
                suffix += 1
            used_ids.add(gpu_id)

            detail_parts: List[str] = []
            if pci_address:
                detail_parts.append("Устройство: " + pci_address)
            if provider:
                detail_parts.append("Поставщик: " + provider)
            gpus.append(
                Gpu(
                    id=gpu_id,
                    name=description,
                    vendor=vendor,
                    kind=kind,
                    driver=driver,
                    memory_mb=memory_mb,
                    pci_address=pci_address,
                    detail=" · ".join(detail_parts),
                )
            )

        gpus.sort(key=lambda item: _KIND_ORDER.get(item.kind, 9))
        return gpus

    # -- browsers ----------------------------------------------------------
    def list_browsers(self) -> List[Browser]:
        return self._guard("list_browsers", self._list_browsers, list)

    def _list_browsers(self) -> List[Browser]:
        browsers: List[Browser] = []
        seen_executables: set = set()
        seen_ids: set = set()

        for root, key_path in START_MENU_INTERNET_ROOTS:
            for child in self._registry.list_subkeys(root, key_path):
                child = str(child or "").strip()
                if not child:
                    continue
                base_path = key_path + "\\" + child
                command_line = (
                    self._registry.get_string(root, base_path + r"\shell\open\command", "")
                    or ""
                )
                executable = _command_executable(command_line)
                if not executable:
                    continue
                normalized = _normcase(executable)
                if normalized in seen_executables:
                    continue
                if os.path.basename(executable).lower() in IE_EXECUTABLES:
                    continue
                if not self._file_exists(executable):
                    continue
                display = (
                    self._registry.get_string(root, base_path, "") or ""
                ).strip()
                name = display or _clean_client_name(child) or os.path.basename(executable)
                version = (
                    self._registry.get_string(root, base_path, "Version") or ""
                ).strip()
                browser = self._make_browser(
                    name=name,
                    executable=executable,
                    command_line=command_line,
                    source="registry",
                    id_hint="windows:" + _slug(child),
                    seen_ids=seen_ids,
                    version=version,
                )
                browsers.append(browser)
                seen_executables.add(normalized)

        if not browsers:
            browsers = self._fallback_browsers(seen_ids)

        browsers.sort(key=lambda item: item.name.casefold())
        return browsers

    def _make_browser(
        self,
        name: str,
        executable: str,
        command_line: str,
        source: str,
        id_hint: str,
        seen_ids: set,
        version: str = "",
    ) -> Browser:
        exe_name = os.path.basename(executable).lower()
        argv = [token for token in _split_command(command_line) if token]
        if argv and _normcase(argv[0]) == _normcase(executable):
            launch_command: Tuple[str, ...] = tuple(argv)
        else:
            launch_command = (executable,)

        browser_id = id_hint
        suffix = 2
        while browser_id in seen_ids:
            browser_id = f"{id_hint}-{suffix}"
            suffix += 1
        seen_ids.add(browser_id)

        return Browser(
            id=browser_id,
            name=name,
            executable=executable,
            launch_command=launch_command,
            engine=_engine_for(exe_name, name),
            version=version,
            process_names=(exe_name,) if exe_name else (),
            source=source,
            supported=True,
        )

    def _program_roots(self) -> List[str]:
        roots: List[str] = []
        for env_name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
            try:
                value = os.environ.get(env_name) or ""
            except Exception:  # pragma: no cover - defensive
                value = ""
            if value and value not in roots:
                roots.append(value)
        if not roots:  # pragma: no cover - only on very unusual hosts
            roots = [r"C:\Program Files", r"C:\Program Files (x86)"]
        return roots

    def _fallback_browsers(self, seen_ids: set) -> List[Browser]:
        """Find well-known browsers in their conventional install folders."""
        roots = self._program_roots()
        browsers: List[Browser] = []
        seen_executables: set = set()
        for name, exe_name, engine, relatives in _WELL_KNOWN_BROWSERS:
            found = ""
            for relative in relatives:
                for root in roots:
                    candidate = os.path.join(root, relative)
                    if self._file_exists(candidate):
                        found = candidate
                        break
                if found:
                    break
            if not found:
                continue
            normalized = _normcase(found)
            if normalized in seen_executables:
                continue
            seen_executables.add(normalized)
            browser_id = "windows:" + _slug(os.path.splitext(exe_name)[0])
            suffix = 2
            while browser_id in seen_ids:
                browser_id = f"{browser_id}-{suffix}"
                suffix += 1
            seen_ids.add(browser_id)
            browsers.append(
                Browser(
                    id=browser_id,
                    name=name,
                    executable=found,
                    launch_command=(found,),
                    engine=engine or _engine_for(exe_name, name),
                    process_names=(exe_name,),
                    source="well-known",
                    supported=True,
                )
            )
        return browsers

    # -- options -----------------------------------------------------------
    def list_options(self) -> List[GpuOption]:
        return self._guard("list_options", self._list_options, self._fallback_options)

    def _fallback_options(self) -> List[GpuOption]:
        return self._list_options(use_gpus=False)

    def _list_options(self, use_gpus: bool = True) -> List[GpuOption]:
        gpus = self.list_gpus() if use_gpus else []
        integrated = next((item for item in gpus if item.kind == "integrated"), None)
        discrete = next((item for item in gpus if item.kind == "discrete"), None)

        power_label = (
            "Энергосбережение — " + integrated.name
            if integrated is not None
            else "Энергосбережение — встроенная видеокарта"
        )
        high_label = (
            "Высокая производительность — " + discrete.name
            if discrete is not None
            else "Высокая производительность — дискретная видеокарта"
        )

        return [
            GpuOption(
                id=WINDOWS_OPTION_DEFAULT,
                label="По умолчанию — Windows выбирает сам",
                description="Windows сам решает, какую видеокарту использовать для браузера.",
                kind="auto",
                payload={"preference": WINDOWS_PREF_DEFAULT},
            ),
            GpuOption(
                id=WINDOWS_OPTION_POWER_SAVING,
                label=power_label,
                description="Встроенная графика: тише и экономичнее, но слабее в играх и 3D.",
                kind="integrated",
                gpu_id=integrated.id if integrated is not None else "",
                payload={"preference": WINDOWS_PREF_POWER_SAVING},
            ),
            GpuOption(
                id=WINDOWS_OPTION_HIGH_PERFORMANCE,
                label=high_label,
                description="Дискретная видеокарта: максимальная производительность, выше расход энергии.",
                kind="discrete",
                gpu_id=discrete.id if discrete is not None else "",
                payload={"preference": WINDOWS_PREF_HIGH_PERFORMANCE},
            ),
        ]

    def _fallback_default_option(self) -> GpuOption:
        return GpuOption(
            id=WINDOWS_OPTION_DEFAULT,
            label="По умолчанию — Windows выбирает сам",
            description="Windows сам решает, какую видеокарту использовать для браузера.",
            kind="auto",
            payload={"preference": WINDOWS_PREF_DEFAULT},
        )

    def _find_option(self, option: GpuOption) -> Optional[GpuOption]:
        for item in self.list_options():
            if item.id == getattr(option, "id", None):
                return item
        return None

    # -- current option ----------------------------------------------------
    def current_option(self, browser: Browser) -> GpuOption:
        return self._guard(
            "current_option",
            lambda: self._current_option(browser),
            self._fallback_default_option,
        )

    def _current_option(self, browser: Browser) -> GpuOption:
        options = self.list_options() or [self._fallback_default_option()]
        executable = (getattr(browser, "executable", "") or "").strip()
        if not executable:
            return options[0]
        data = self._read_preference(executable)
        preference = _parse_preference(data)
        for option in options:
            if _preference_for_option(option) == preference:
                return option
        return options[0]

    def _read_preference(self, executable: str) -> Optional[str]:
        value_name = self._find_value_name(executable)
        try:
            data = self._registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, value_name)
        except Exception as exc:
            self._record_error("read_preference", exc)
            return None
        if data is None and value_name != executable:
            try:
                data = self._registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, executable)
            except Exception as exc:
                self._record_error("read_preference", exc)
                return None
        return data

    def _find_value_name(self, executable: str) -> str:
        """Return the existing value name or the executable path itself."""
        executable = str(executable or "")
        target = _normcase(executable)
        if not target:
            return executable
        try:
            for name, _value, _value_type in self._registry.list_values(
                HKCU, WINDOWS_GPU_PREFS_KEY
            ):
                if _normcase(name) == target:
                    return str(name)
        except Exception as exc:
            self._record_error("find_value_name", exc)
        return executable

    # -- process checks ----------------------------------------------------
    def _process_entries(self) -> List[RunningProcess]:
        provider = self._processes
        if provider is None:
            return []
        for attribute in ("processes", "snapshot"):
            collector = getattr(provider, attribute, None)
            if callable(collector):
                try:
                    return self._normalise_processes(collector())
                except Exception as exc:
                    self._record_error("processes." + attribute, exc)
                    return []
        paths: List[Any] = []
        collector = getattr(provider, "running_paths", None)
        if callable(collector):
            try:
                paths = list(collector() or [])
            except Exception as exc:
                self._record_error("processes.running_paths", exc)
                return []
        pids: List[Any] = []
        pid_collector = getattr(provider, "pids", None)
        if callable(pid_collector):
            try:
                pids = list(pid_collector() or [])
            except Exception:
                pids = []
        entries: List[RunningProcess] = []
        for index, item in enumerate(paths):
            if not isinstance(item, str):
                entries.extend(self._normalise_processes([item]))
                continue
            pid = 0
            if index < len(pids) and isinstance(pids[index], int):
                pid = int(pids[index])
            entries.append(
                RunningProcess(pid=pid or index + 1, path=item, name=os.path.basename(item))
            )
        return entries

    def _normalise_processes(self, raw: Iterable[Any]) -> List[RunningProcess]:
        entries: List[RunningProcess] = []
        for index, item in enumerate(list(raw or [])):
            try:
                if isinstance(item, RunningProcess):
                    entries.append(item)
                    continue
                if isinstance(item, str):
                    entries.append(
                        RunningProcess(pid=index + 1, path=item, name=os.path.basename(item))
                    )
                    continue
                if isinstance(item, dict):
                    path = str(item.get("path") or item.get("exe") or "")
                    name = str(item.get("name") or os.path.basename(path))
                    entries.append(RunningProcess(int(item.get("pid") or 0), path, name))
                    continue
                values = list(item)
                if len(values) >= 3:
                    path = str(values[1] or "")
                    name = str(values[2] or os.path.basename(path))
                    entries.append(RunningProcess(int(values[0] or 0), path, name))
                elif len(values) == 2:
                    first, second = values
                    if isinstance(first, int) and not isinstance(second, int):
                        path = str(second or "")
                        entries.append(
                            RunningProcess(int(first), path, os.path.basename(path))
                        )
                    else:
                        path = str(first or "")
                        pid = int(second) if isinstance(second, int) else 0
                        entries.append(
                            RunningProcess(pid, path, os.path.basename(path))
                        )
            except Exception as exc:  # pragma: no cover - defensive
                self._record_error("normalise_processes", exc)
                continue
        return entries

    def _browser_process_names(self, browser: Browser) -> set:
        names = set()
        for name in getattr(browser, "process_names", ()) or ():
            text = str(name or "").strip().lower()
            if text:
                names.add(text)
        executable = (getattr(browser, "executable", "") or "").strip()
        exe_name = os.path.basename(executable).lower()
        if exe_name:
            names.add(exe_name)
        return names

    def _browser_matches(self, browser: Browser, entry: RunningProcess) -> bool:
        names = self._browser_process_names(browser)
        executable = (getattr(browser, "executable", "") or "").strip()
        if not names and not executable:
            return False
        entry_name = str(entry.name or "").strip().lower()
        if not entry_name and entry.path:
            entry_name = os.path.basename(entry.path).lower()
        if entry_name and entry_name in names:
            return True
        if entry.path and executable and _normcase(entry.path) == _normcase(executable):
            return True
        if entry.path and os.path.basename(entry.path).lower() in names:
            return True
        return False

    def running_pids(self, browser: Browser) -> List[int]:
        return self._guard("running_pids", lambda: self._running_pids(browser), list)

    def _running_pids(self, browser: Browser) -> List[int]:
        pids: List[int] = []
        for entry in self._process_entries():
            if self._browser_matches(browser, entry) and entry.pid not in pids:
                pids.append(entry.pid)
        return pids

    def is_browser_running(self, browser: Browser) -> bool:
        return self._guard(
            "is_browser_running",
            lambda: bool(self._running_pids(browser)),
            lambda: False,
        )

    # -- apply -------------------------------------------------------------
    def apply(self, browser: Browser, option: GpuOption) -> ApplyResult:
        return self._guard(
            "apply",
            lambda: self._apply(browser, option),
            lambda: ApplyResult.failure(
                "Не удалось применить настройку. Подробности в диагностике."
            ),
        )

    def _apply(self, browser: Browser, option: GpuOption) -> ApplyResult:
        known = self._find_option(option)
        if known is None:
            return ApplyResult.failure(
                "Неизвестный вариант настройки графики. Обновите список и попробуйте снова."
            )
        preference = _preference_for_option(known)
        if preference is None:
            return ApplyResult.failure(
                "Неизвестный вариант настройки графики. Обновите список и попробуйте снова."
            )

        executable = (getattr(browser, "executable", "") or "").strip()
        if not executable:
            return ApplyResult.failure(
                "Не удалось определить путь к исполняемому файлу браузера."
            )

        if self._running_pids(browser):
            return ApplyResult.failure(
                "Браузер ещё запущен. Закройте его полностью и повторите попытку."
            )

        entry_key = self._state_key(browser)
        existing = self._state.get(entry_key)
        previous = (
            existing
            if isinstance(existing, dict)
            and str(existing.get("platform", "")).lower() == WINDOWS
            else None
        )

        value_name = self._find_value_name(executable)
        current_data = self._read_current_value_data(executable, value_name)

        if preference == WINDOWS_PREF_DEFAULT:
            if previous is not None:
                original_exists = bool(previous.get("original_exists", False))
                original_data = str(previous.get("original_data") or "")
                original_name = str(previous.get("value_name") or executable)
                try:
                    self._restore_value(original_name, original_exists, original_data)
                except OSError as exc:
                    self._record_error("apply.restore_default", exc)
                    return ApplyResult.failure(
                        "Не удалось вернуть настройки по умолчанию для этого браузера.",
                        details=f"{type(exc).__name__}: {exc}",
                    )
                self._state.delete(entry_key)
                return ApplyResult.success(
                    f"Для браузера «{browser.name}» возвращены настройки по умолчанию."
                )
            try:
                removed = self._delete_value(executable)
            except OSError as exc:
                self._record_error("apply.delete_default", exc)
                return ApplyResult.failure(
                    "Не удалось вернуть настройки по умолчанию для этого браузера.",
                    details=f"{type(exc).__name__}: {exc}",
                )
            if removed:
                return ApplyResult.success(
                    f"Для браузера «{browser.name}» возвращены настройки по умолчанию."
                )
            return ApplyResult.success(
                f"Для браузера «{browser.name}» уже действуют настройки по умолчанию."
            )

        has_original = (
            previous is not None
            and "original_exists" in previous
            and "original_data" in previous
        )
        if has_original:
            original_exists = bool(previous.get("original_exists"))
            original_data = str(previous.get("original_data") or "")
            original_name = str(previous.get("value_name") or executable)
        else:
            original_exists = current_data is not None
            original_data = current_data or ""
            original_name = value_name

        new_data = _compose_preference(current_data or "", preference)
        try:
            self._registry.set_string(HKCU, WINDOWS_GPU_PREFS_KEY, value_name, new_data)
        except OSError as exc:
            self._record_error("apply.set_string", exc)
            return ApplyResult.failure(
                "Не удалось сохранить настройку в настройках Windows.",
                details=f"{type(exc).__name__}: {exc}",
            )

        entry = {
            "platform": WINDOWS,
            "browser_id": str(getattr(browser, "id", "") or ""),
            "browser_name": str(getattr(browser, "name", "") or ""),
            "option_id": known.id,
            "option_label": known.label,
            "applied_at": self._time_now(),
            "description": f"{browser.name}: {known.label}",
            "original_exists": original_exists,
            "original_data": original_data,
            "value_name": original_name,
            "executable": executable,
            "gpu_preference": preference,
        }
        self._state.put(entry_key, entry)
        details = (
            f"Раздел реестра: HKCU\\{WINDOWS_GPU_PREFS_KEY}\n"
            f"Значение: {value_name} = {new_data}\n"
            "Изменение вступит в силу после полного перезапуска браузера."
        )
        return ApplyResult.success(
            f"Готово! Для браузера «{browser.name}» выбрано: {known.label}.",
            details=details,
        )

    def _read_current_value_data(
        self, executable: str, value_name: str
    ) -> Optional[str]:
        try:
            data = self._registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, value_name)
            if data is None and value_name != executable:
                data = self._registry.get_string(
                    HKCU, WINDOWS_GPU_PREFS_KEY, executable
                )
            return data
        except Exception as exc:
            self._record_error("read_current_value", exc)
            return None

    def _delete_value(self, value_name: str) -> bool:
        target = self._find_value_name(value_name) or value_name
        try:
            existing = self._registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, target)
        except Exception:
            existing = None
        if existing is None:
            return False
        self._registry.delete_value(HKCU, WINDOWS_GPU_PREFS_KEY, target)
        return True

    def _restore_value(
        self, value_name: str, original_exists: bool, original_data: str
    ) -> None:
        if original_exists:
            target = self._find_value_name(value_name) or value_name
            self._registry.set_string(
                HKCU, WINDOWS_GPU_PREFS_KEY, target, original_data
            )
        else:
            self._delete_value(value_name)

    def _state_key(self, browser: Browser) -> str:
        executable = (getattr(browser, "executable", "") or "").strip()
        if not executable:  # pragma: no cover - defensive
            executable = str(getattr(browser, "id", "") or "unknown")
        return "windows:" + _normcase(executable)

    # -- pending changes / restore ----------------------------------------
    def pending_changes(self) -> List[PendingChange]:
        return self._guard("pending_changes", self._pending_changes, list)

    def _pending_changes(self) -> List[PendingChange]:
        changes: List[PendingChange] = []
        for key, entry in self._state.items():
            if not isinstance(entry, dict):
                continue
            if str(entry.get("platform", "")).lower() != WINDOWS:
                continue
            try:
                changes.append(
                    PendingChange(
                        key=key,
                        platform=WINDOWS,
                        browser_id=str(entry.get("browser_id") or ""),
                        browser_name=str(entry.get("browser_name") or ""),
                        option_id=str(entry.get("option_id") or ""),
                        option_label=str(entry.get("option_label") or ""),
                        applied_at=str(entry.get("applied_at") or ""),
                        description=str(entry.get("description") or ""),
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive
                self._record_error("pending_changes", exc)
                continue
        changes.sort(key=lambda item: item.applied_at)
        return changes

    def restore_all(self) -> ApplyResult:
        return self._guard(
            "restore_all",
            self._restore_all,
            lambda: ApplyResult.failure(
                "Не удалось вернуть настройки. Подробности в диагностике."
            ),
        )

    def _restore_all(self) -> ApplyResult:
        entries = [
            (key, entry)
            for key, entry in self._state.items()
            if isinstance(entry, dict)
            and str(entry.get("platform", "")).lower() == WINDOWS
        ]
        if not entries:
            return ApplyResult.success("Возвращать нечего: изменений нет.")

        restored: List[str] = []
        failures: List[str] = []
        for key, entry in entries:
            label = str(entry.get("browser_name") or entry.get("executable") or key)
            try:
                self._restore_entry(key, entry)
                restored.append(label)
            except Exception as exc:
                self._record_error("restore_all", exc)
                failures.append(f"{label}: {type(exc).__name__}: {exc}")

        if not restored:
            return ApplyResult.failure(
                "Не удалось вернуть настройки к исходным. Подробности в диагностике.",
                details="\n".join(failures),
            )
        message = "Настройки возвращены к исходным: " + ", ".join(restored) + "."
        if failures:
            return ApplyResult.success(
                message,
                warnings=["Не удалось вернуть: " + item for item in failures],
            )
        return ApplyResult.success(message)

    def restore_browser(self, browser: Browser) -> ApplyResult:
        return self._guard(
            "restore_browser",
            lambda: self._restore_browser(browser),
            lambda: ApplyResult.failure(
                "Не удалось вернуть настройки браузера. Подробности в диагностике."
            ),
        )

    def _restore_browser(self, browser: Browser) -> ApplyResult:
        key = self._state_key(browser)
        entry = self._state.get(key)
        if not isinstance(entry, dict) or str(entry.get("platform", "")).lower() != WINDOWS:
            return ApplyResult.success("Для этого браузера нет сохранённых изменений.")
        try:
            self._restore_entry(key, entry)
        except Exception as exc:
            self._record_error("restore_browser", exc)
            return ApplyResult.failure(
                "Не удалось вернуть настройки браузера. Подробности в диагностике.",
                details=f"{type(exc).__name__}: {exc}",
            )
        return ApplyResult.success(
            f"Настройки браузера «{browser.name}» возвращены к исходным."
        )

    def _restore_entry(self, key: str, entry: Dict[str, Any]) -> None:
        value_name = str(entry.get("value_name") or entry.get("executable") or "").strip()
        if not value_name:
            raise ValueError("в настройках не сохранён путь к браузеру")
        original_exists = bool(entry.get("original_exists", False))
        original_data = str(entry.get("original_data") or "")
        self._restore_value(value_name, original_exists, original_data)
        self._state.delete(key)

    # -- launching ---------------------------------------------------------
    def launch(self, browser: Browser) -> LaunchResult:
        return self._guard(
            "launch",
            lambda: self._launch(browser),
            lambda: LaunchResult(
                ok=False, message="Не удалось запустить браузер. Подробности в диагностике."
            ),
        )

    def _launch(self, browser: Browser) -> LaunchResult:
        command: List[str] = []
        for part in getattr(browser, "command", ()) or ():
            text = str(part or "").strip()
            if text:
                command.append(text)
        if not command:
            return LaunchResult(
                ok=False, message="Не удалось определить команду запуска браузера."
            )
        if len(command) > 1 and all(_PLACEHOLDER_RE.search(part) for part in command[1:]):
            # Placeholders like "%1" only make sense inside a shell context.
            command = command[:1]
        executable = command[0]
        if not self._file_exists(executable):
            return LaunchResult(
                ok=False,
                message="Не удалось найти файл браузера. Возможно, он был удалён.",
            )
        if self._running_pids(browser):
            return LaunchResult(ok=False, message="Браузер уже запущен.")
        launcher = getattr(self._system, "launch", None)
        if callable(launcher):
            try:
                pid = int(launcher(command) or 0)
            except Exception as exc:
                self._record_error("launch", exc)
                return LaunchResult(
                    ok=False,
                    message="Не удалось запустить браузер. Подробности в диагностике.",
                )
            return LaunchResult(ok=True, message=f"Запускаю {browser.name}.", pid=pid)
        try:
            pid = _popen_detached(command)
        except Exception as exc:
            self._record_error("launch", exc)
            return LaunchResult(
                ok=False,
                message="Не удалось запустить браузер. Подробности в диагностике.",
            )
        return LaunchResult(ok=True, message=f"Запускаю {browser.name}.", pid=pid)

    # -- hints / diagnostics ----------------------------------------------
    def notes(self) -> List[str]:
        return self._guard(
            "notes",
            lambda: [
                "Настройка сохраняется только для вашей учётной записи Windows — права администратора не нужны.",
                "Изменение начнёт действовать после полного закрытия и повторного запуска браузера.",
                "Windows 10 и Windows 11: используется системный параметр «Графические процессоры» (GpuPreference).",
                "Если браузер запущен, закройте все его окна и фоновые процессы, а затем повторите попытку.",
            ],
            list,
        )

    def diagnostics(self) -> str:
        try:
            return self._diagnostics()
        except Exception as exc:  # pragma: no cover - defensive
            self._record_error("diagnostics", exc)
            return "Backend: WindowsBackend\nDiagnostics failed: " + str(exc)

    def _diagnostics(self) -> str:
        os_info = self.os_info()
        gpus = self.list_gpus()
        browsers = self.list_browsers()
        options = self.list_options()
        pending = self.pending_changes()
        registry = self._registry
        registry_available = bool(getattr(registry, "available", True))
        registry_error = str(getattr(registry, "last_error", "") or "")
        process_count = len(self._process_entries())
        process_error = str(getattr(self._processes, "last_error", "") or "")

        lines: List[str] = [
            "Backend: WindowsBackend",
            "Windows: " + os_info.pretty,
            "Registry: "
            + ("доступен" if registry_available else "недоступен")
            + " (чтение; запись только в HKCU текущего пользователя)",
            "GPU key: HKLM\\" + GPU_CLASS_KEY,
        ]
        if registry_error:
            lines.append("Registry warning: " + registry_error)
        lines.append(f"GPUs: {len(gpus)}")
        for gpu in gpus:
            lines.append(
                f"  - {gpu.name} [{gpu.vendor}, {gpu.kind}] driver "
                f"{gpu.driver or 'н/д'} memory {gpu.memory_mb} MB "
                f"pci {gpu.pci_address or 'н/д'} id {gpu.id}"
            )
        lines.append(f"Browsers: {len(browsers)}")
        for browser in browsers:
            lines.append(
                f"  - {browser.name} — {browser.executable} "
                f"({browser.engine}, {browser.source})"
            )
        lines.append(f"Options: {len(options)}")
        for option in options:
            lines.append(f"  - {option.id}: {option.label}")
        lines.append(f"Processes visible: {process_count}")
        if process_error:
            lines.append("Process warning: " + process_error)
        lines.append(f"Pending changes: {len(pending)}")
        for change in pending:
            lines.append(
                f"  - {change.browser_name}: {change.option_label} ({change.applied_at})"
            )
        try:
            lines.append("State file: " + str(self._state.state_file))
        except Exception:  # pragma: no cover - defensive
            pass
        if self._errors:
            lines.append(f"Errors ({len(self._errors)}):")
            for error in self._errors[-10:]:
                lines.append("  " + error)
        return "\n".join(lines)

    def close(self) -> None:
        """Release resources (the backend keeps no handles open)."""
        # Nothing to release: every registry/process handle is closed right
        # after use.  Kept for protocol completeness.
        return None


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------
def _classify_vendor(provider: str, matching: str, description: str = "") -> str:
    haystack = f"{provider or ''} {matching or ''} {description or ''}".lower()
    if "nvidia" in haystack or "ven_10de" in haystack:
        return "nvidia"
    if (
        "advanced micro devices" in haystack
        or "amd" in haystack
        or "ati technologies" in haystack
        or "ven_1002" in haystack
    ):
        return "amd"
    if "intel" in haystack or "ven_8086" in haystack:
        return "intel"
    if "microsoft" in haystack or "basic render" in haystack:
        return "microsoft"
    if any(
        needle in haystack
        for needle in ("virtual", "vmware", "ven_15ad", "ven_1af4", "ven_1234")
    ):
        return "virtual"
    return "other"


def _classify_kind(vendor: str, description: str = "") -> str:
    if vendor == "microsoft" or "basic render" in str(description or "").lower():
        return "virtual"
    if vendor == "intel":
        return "integrated"
    if vendor in ("nvidia", "amd"):
        return "discrete"
    return "unknown"


def _memory_mb(values: Dict[str, Tuple[Any, int]]) -> int:
    for key in (
        "hardwareinformation.qwmemorysize",
        "hardwareinformation.memorysize",
        "hardwareinformation.vram",
        "qwmemorysize",
        "memorysize",
    ):
        if key not in values:
            continue
        raw = _coerce_int(values[key][0])
        if raw > 0:
            return max(1, int(round(raw / (1024 * 1024))))
    return 0


def _parse_pci(matching: str) -> Tuple[str, str, str]:
    text = str(matching or "").strip()
    match = _PCI_RE.search(text)
    if not match:
        return (text, "", "")
    return (match.group(1).upper(), match.group(2), match.group(3))


__all__ = [
    "CREATE_NEW_PROCESS_GROUP",
    "DETACHED_PROCESS",
    "GPU_CLASS_KEY",
    "HKCU",
    "HKLM",
    "RunningProcess",
    "START_MENU_INTERNET_ROOTS",
    "WindowsBackend",
    "WindowsProcessProvider",
    "WindowsRegistry",
    "WindowsSystem",
]
