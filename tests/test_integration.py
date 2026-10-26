r"""Integration / acceptance tests for GPU Switch (QA deliverable).

Covers the customer's ten requirements end to end through stable seams:

* the real command line (subprocess, mock and live Windows backends);
* WindowsBackend against a fake registry / process provider / launcher;
* LinuxBackend against a fixture filesystem world;
* StateStore persistence + corrupt-state quarantine;
* the Tk UI controller against the fake Windows world (no real GUI shown).

The tests are self-contained (stdlib unittest only) and write temporary files
under tests/.tmp, matching the other test modules in this repository.

Run with:  C:\Python313\python.exe -m unittest tests.test_integration -v
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
TMP_ROOT = Path(__file__).resolve().parent / ".tmp"
PYTHON = sys.executable or "python"

from app.interface import (  # noqa: E402
    LINUX,
    LINUX_OPTION_DEFAULT,
    LINUX_OPTION_NVIDIA_OFFLOAD,
    MOCK,
    WINDOWS,
    WINDOWS_GPU_PREFS_KEY,
    WINDOWS_OPTION_DEFAULT,
    WINDOWS_OPTION_HIGH_PERFORMANCE,
    WINDOWS_OPTION_POWER_SAVING,
    Browser,
)
from app.platforms.linux import LinuxBackend  # noqa: E402
from app.platforms.windows import (  # noqa: E402
    GPU_CLASS_KEY,
    HKCU,
    HKLM,
    WindowsBackend,
)
from app.state import StateStore  # noqa: E402

try:  # Tk may be unavailable on a headless runner; skip only the GUI class then.
    import tkinter as tk
    from tkinter import ttk

    import app.ui as ui

    TK_AVAILABLE = True
    TK_ERROR = ""
except Exception as exc:  # pragma: no cover - environment dependent
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    ui = None  # type: ignore[assignment]
    TK_AVAILABLE = False
    TK_ERROR = f"{type(exc).__name__}: {exc}"


TEXT_NEEDS_TK = "Tk unavailable: " + TK_ERROR


# ---------------------------------------------------------------------------
# Temporary directories (sandbox-friendly: tempfile.mkdtemp is not removable
# under the DSH sandbox ACLs, so mirror the other test modules and use .tmp).
# ---------------------------------------------------------------------------
def make_temp_dir(prefix: str = "integration-") -> Path:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    for _ in range(50):
        candidate = TMP_ROOT / (prefix + uuid.uuid4().hex[:12])
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError("could not create a temporary directory under " + str(TMP_ROOT))


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._temp_dirs: list[Path] = []

    def temp_dir(self, prefix: str = "integration-") -> Path:
        path = make_temp_dir(prefix)
        self._temp_dirs.append(path)
        return path

    def tearDown(self) -> None:
        for path in reversed(self._temp_dirs):
            shutil.rmtree(path, ignore_errors=True)
        super().tearDown()


# ---------------------------------------------------------------------------
# CLI acceptance tests (subprocess; mock + live Windows backend).
# ---------------------------------------------------------------------------
def run_cli(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env.pop("DISPLAY", None)  # not needed on Windows, harmless elsewhere
    return subprocess.run(
        [PYTHON, str(WORKSPACE / "main.py"), *args],
        cwd=str(WORKSPACE),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def combined(completed: subprocess.CompletedProcess) -> str:
    return (completed.stdout or "") + "\n" + (completed.stderr or "")


class CliAcceptanceTests(TempDirTestCase):
    """Requirement 1/2/3 surface via --diagnostics; GUI startup via smoke test."""

    def test_self_test_mock_backend_passes(self) -> None:
        completed = run_cli("--self-test", "--mock")
        output = combined(completed)
        self.assertEqual(completed.returncode, 0, msg=output)
        self.assertIn("PASS", completed.stdout)
        self.assertIn("mock", completed.stdout.lower())
        self.assertNotIn("FAIL", completed.stdout)

    def test_self_test_live_windows_backend(self) -> None:
        completed = run_cli("--self-test")
        output = combined(completed)
        # Pass/fail may depend on the sandbox (registry writes are denied), but
        # the run must terminate cleanly, print a report and never crash.
        self.assertIn(completed.returncode, (0, 1), msg=output)
        self.assertIn("PASS", completed.stdout)
        self.assertNotIn("Traceback (most recent call last)", completed.stderr)
        self.assertEqual(completed.returncode == 0, "FAIL" not in completed.stdout, msg=output)

    def test_diagnostics_mock_lists_platform_gpus_browsers(self) -> None:
        completed = run_cli("--diagnostics", "--mock")
        output = combined(completed)
        self.assertEqual(completed.returncode, 0, msg=output)
        lowered = output.lower()
        self.assertIn("диагностик", lowered)
        self.assertIn("mock", lowered)
        self.assertIn("видеокарты", lowered)
        self.assertIn("браузеры", lowered)
        self.assertIn("конец отчёта", lowered)

    def test_diagnostics_live_windows(self) -> None:
        completed = run_cli("--diagnostics")
        output = combined(completed)
        self.assertEqual(completed.returncode, 0, msg=output)
        lowered = output.lower()
        self.assertIn("windows", lowered)
        self.assertIn("windowsbackend", lowered)
        self.assertIn("видеокарты", lowered)
        self.assertIn("браузеры", lowered)
        self.assertIn("конец отчёта", lowered)
        self.assertNotIn("Traceback (most recent call last)", completed.stderr)

    def test_ui_smoke_test_starts_and_closes_window(self) -> None:
        if not TK_AVAILABLE:
            self.skipTest(TEXT_NEEDS_TK)
        completed = run_cli("--ui-smoke-test")
        output = combined(completed)
        self.assertEqual(completed.returncode, 0, msg=output)
        self.assertIn("Смоук-тест интерфейса прошёл успешно", completed.stdout)

    def test_unknown_argument_exits_nonzero_without_traceback(self) -> None:
        completed = run_cli("--definitely-not-a-real-flag")
        output = combined(completed)
        self.assertNotEqual(completed.returncode, 0, msg=output)
        self.assertNotIn("Traceback (most recent call last)", completed.stderr)


class UiTextTests(TempDirTestCase):
    """Requirement 9 (exact success wording), Russian UI, no-admin static check."""

    def test_ready_dialog_text_is_exact(self) -> None:
        if not TK_AVAILABLE:
            self.skipTest(TEXT_NEEDS_TK)
        self.assertEqual(ui.READY_TITLE, "Все настроено, запустите браузер")
        self.assertEqual(ui.LAUNCH_BUTTON, "Запустить браузер")
        self.assertIn("{browser}", ui.READY_DETAIL)
        self.assertIn("{option}", ui.READY_DETAIL)

    def test_restore_everything_button_text(self) -> None:
        if not TK_AVAILABLE:
            self.skipTest(TEXT_NEEDS_TK)
        self.assertEqual(ui.RESTORE_ALL_BUTTON, "Вернуть всё назад")
        self.assertEqual(ui.RESTORE_ALL_TITLE, "Вернуть всё назад")
        self.assertTrue(ui.RESTORE_ALL_CONFIRM)

    def test_window_title_and_russian_ui(self) -> None:
        if not TK_AVAILABLE:
            self.skipTest(TEXT_NEEDS_TK)
        self.assertEqual(ui.WINDOW_TITLE, "GPU Switch")
        self.assertEqual(ui.BROWSER_PROMPT, "Выберите браузер из обнаруженных на вашем ПК")
        self.assertTrue(ui.CURRENT_PREFIX.startswith("Сейчас включён ускоритель"))
        self.assertIn("Закройте", ui.RUNNING_WARNING)
        self.assertEqual(ui.CHECK_AGAIN_BUTTON, "Проверить снова")
        self.assertEqual(ui.APPLY_BUTTON, "Применить")
        # Russian UI: every user-visible constant must contain Cyrillic text.
        for constant in (
            ui.READY_TITLE,
            ui.LAUNCH_BUTTON,
            ui.RESTORE_ALL_BUTTON,
            ui.BROWSER_PROMPT,
            ui.RUNNING_WARNING,
            ui.CHECK_AGAIN_BUTTON,
            ui.APPLY_BUTTON,
            ui.PENDING_EMPTY,
        ):
            self.assertRegex(constant, "[А-Яа-яЁё]", msg=constant)

    def test_no_privilege_elevation_apis_in_source(self) -> None:
        forbidden = (
            "runas",
            "shellexecute",
            "isuseranadmin",
            "requireadministrator",
            "pkexec",
        )
        sources = [WORKSPACE / "main.py", WORKSPACE / "app" / "main.py"]
        sources.extend(sorted((WORKSPACE / "app").rglob("*.py")))
        self.assertTrue(any(path.is_file() for path in sources))
        for path in sources:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8").lower()
            for token in forbidden:
                self.assertNotIn(token, text, msg=str(path) + ": contains " + token)


# ---------------------------------------------------------------------------
# Windows fake world (mirrors tests/test_windows.py so this file stays
# self-contained and does not depend on a teammate's test module).
# ---------------------------------------------------------------------------
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
FIREFOX_EXE = r"C:\Program Files\Firefox Developer Edition\firefox.exe"
YANDEX_EXE = r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe"
IE_EXE = r"C:\Program Files\Internet Explorer\iexplore.exe"
SAMPLE_EXISTING = (CHROME_EXE, EDGE_EXE, FIREFOX_EXE, YANDEX_EXE)

START_KEY = r"SOFTWARE\Clients\StartMenuInternet"
GPU_ROOT = GPU_CLASS_KEY


def key_id(root: str, path: str) -> tuple[str, str]:
    return (str(root).upper(), str(path).replace("/", "\\").strip("\\").lower())


class FakeRegistry:
    def __init__(self) -> None:
        self.available = True
        self.last_error = ""
        self.keys: dict[tuple[str, str], dict] = {}
        self.write_calls: list[tuple[str, str, str, str]] = []
        self.delete_calls: list[tuple[str, str, str]] = []
        self.write_error: BaseException | None = None
        self.delete_error: BaseException | None = None

    def ensure_key(self, root: str, path: str) -> dict:
        ident = key_id(root, path)
        if ident not in self.keys:
            self.keys[ident] = {"values": {}, "subkeys": {}}
        return self.keys[ident]

    def add_key(self, root: str, path: str) -> dict:
        return self.ensure_key(root, path)

    def add_value(self, root: str, path: str, name: str, value, value_type: int = 1) -> None:
        key = self.ensure_key(root, path)
        key["values"][str(name).lower()] = (str(name), value, int(value_type))

    def add_subkey(self, root: str, parent: str, child: str) -> dict:
        key = self.ensure_key(root, parent)
        key["subkeys"][child.lower()] = child
        return self.ensure_key(root, parent + "\\" + child)

    def get_value(self, root: str, path: str, name: str = ""):
        key = self.keys.get(key_id(root, path))
        if key is None:
            return None
        entry = key["values"].get(str(name).lower())
        return None if entry is None else entry[1]

    def get_string(self, root: str, path: str, name: str = ""):
        value = self.get_value(root, path, name)
        return None if value is None else str(value)

    def list_values(self, root: str, path: str) -> list[tuple[str, object, int]]:
        key = self.keys.get(key_id(root, path))
        return [] if key is None else list(key["values"].values())

    def list_subkeys(self, root: str, path: str) -> list[str]:
        key = self.keys.get(key_id(root, path))
        return [] if key is None else list(key["subkeys"].values())

    def set_string(self, root: str, path: str, name: str, data: str) -> None:
        if self.write_error is not None:
            raise self.write_error
        key = self.ensure_key(root, path)
        key["values"][str(name).lower()] = (str(name), str(data), 1)
        self.write_calls.append((root, path, name, data))

    def delete_value(self, root: str, path: str, name: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        key = self.keys.get(key_id(root, path))
        entry = None if key is None else key["values"].get(str(name).lower())
        if entry is None:
            raise FileNotFoundError(str(path) + "\\" + str(name))
        del key["values"][str(name).lower()]
        self.delete_calls.append((root, path, name))


class FakeProcessProvider:
    def __init__(self, paths=(), pids=None) -> None:
        self.paths = list(paths)
        self._pids = [1000 + index for index in range(len(self.paths))] if pids is None else list(pids)
        self.last_error = ""

    def running_paths(self) -> list[str]:
        return list(self.paths)

    def pids(self) -> list[int]:
        return list(self._pids)


class FakeSystem:
    def __init__(self, existing_paths=None) -> None:
        self.existing_paths = None if existing_paths is None else {os.path.normcase(p) for p in existing_paths}
        self.windows_version = (10, 0, 22631)
        self.architecture = "AMD64"
        self.hostname = "TEST-PC"
        self.launched: list[list[str]] = []
        self.launch_pid = 4242

    def windows_version(self) -> tuple[int, int, int]:
        return self.windows_version

    def architecture(self) -> str:
        return self.architecture

    def hostname(self) -> str:
        return self.hostname

    def file_exists(self, path: str) -> bool:
        if self.existing_paths is None:
            return True
        return os.path.normcase(path) in self.existing_paths

    def launch(self, command) -> int:
        self.launched.append(list(command))
        return self.launch_pid


def add_intel_gpu(registry: FakeRegistry, subkey: str = "0000") -> None:
    registry.add_subkey(HKLM, GPU_ROOT, subkey)
    base = GPU_ROOT + "\\" + subkey
    registry.add_value(HKLM, base, "DriverDesc", "Intel(R) UHD Graphics 630")
    registry.add_value(HKLM, base, "ProviderName", "Intel Corporation")
    registry.add_value(HKLM, base, "MatchingDeviceId", r"PCI\VEN_8086&DEV_3E9B")
    registry.add_value(HKLM, base, "DriverVersion", "31.0.101.2140")
    registry.add_value(
        HKLM, base + r"\HardwareInformation", "MemorySize", struct.pack("<I", 0x40000000), 3
    )


def add_nvidia_gpu(registry: FakeRegistry, subkey: str = "0001") -> None:
    registry.add_subkey(HKLM, GPU_ROOT, subkey)
    base = GPU_ROOT + "\\" + subkey
    registry.add_value(HKLM, base, "DriverDesc", "NVIDIA GeForce GTX 1050 Ti")
    registry.add_value(HKLM, base, "ProviderName", "NVIDIA")
    registry.add_value(HKLM, base, "MatchingDeviceId", r"pci\ven_10de&dev_1c8c&subsys_12601025")
    registry.add_value(HKLM, base, "DriverVersion", "32.0.15.8157")
    registry.add_value(
        HKLM,
        base + r"\HardwareInformation",
        "qwMemorySize",
        4294967296,
        11,
    )
    registry.add_value(HKLM, base + r"\HardwareInformation", "ChipType", "GeForce GTX 1050 Ti")


def add_browser(
    registry: FakeRegistry,
    key_name: str,
    display: str,
    command_line: str,
    root: str = HKLM,
    parent: str = START_KEY,
) -> None:
    base = parent + "\\" + key_name
    registry.add_subkey(root, parent, key_name)
    registry.add_value(root, base, "", display)
    registry.add_value(root, base + r"\shell\open\command", "", command_line)


def sample_registry() -> FakeRegistry:
    registry = FakeRegistry()
    registry.add_value(HKLM, GPU_ROOT, "Class", "Display")
    add_intel_gpu(registry)
    add_nvidia_gpu(registry)
    registry.add_subkey(HKLM, GPU_ROOT, "Properties")
    add_browser(registry, "Google Chrome", "Google Chrome", '"' + CHROME_EXE + '"')
    add_browser(registry, "Microsoft Edge", "Microsoft Edge", '"' + EDGE_EXE + '"')
    add_browser(registry, "Firefox-CA9422711AE1A81C", "Firefox Developer Edition", FIREFOX_EXE)
    add_browser(registry, "Yandex", "Yandex", '"' + YANDEX_EXE + '"')
    add_browser(registry, "IEXPLORE.EXE", "Internet Explorer", '"' + IE_EXE + '"')
    return registry


def preference_key(registry: FakeRegistry) -> None:
    registry.add_key(HKCU, WINDOWS_GPU_PREFS_KEY)


class FakeWindowsWorld:
    def __init__(self, state_dir: Path | None = None) -> None:
        self.registry = sample_registry()
        preference_key(self.registry)
        self.processes = FakeProcessProvider()
        self.system = FakeSystem(SAMPLE_EXISTING)
        self.state = StateStore(state_dir or make_temp_dir("win-state-"))
        self.backend = WindowsBackend(
            registry=self.registry,
            process_provider=self.processes,
            state=self.state,
            system=self.system,
        )

    def option(self, option_id: str):
        for option in self.backend.list_options():
            if option.id == option_id:
                return option
        raise AssertionError("option not found: " + option_id)

    def browser(self, name: str):
        for browser in self.backend.list_browsers():
            if browser.name == name:
                return browser
        raise AssertionError("browser not found: " + name)

    def pref_value(self, executable: str = CHROME_EXE):
        for name, value, _value_type in self.registry.list_values(HKCU, WINDOWS_GPU_PREFS_KEY):
            if str(name).lower() == executable.lower():
                return value
        return None

    def state_entries(self) -> dict:
        return dict(self.state.load().get("entries") or {})


class WindowsBackendIntegrationTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.world = FakeWindowsWorld(self.temp_dir("win-state-"))
        self.backend = self.world.backend
        self.chrome = self.world.browser("Google Chrome")

    # Requirement 1 + 3 -----------------------------------------------------
    def test_os_detection(self) -> None:
        info = self.backend.os_info()
        self.assertEqual(info.platform_key, WINDOWS)
        self.assertIn("Windows 11", info.name)
        self.assertTrue(info.name)

    def test_graphics_chips_detection(self) -> None:
        gpus = self.backend.list_gpus()
        self.assertEqual(len(gpus), 2)
        by_name = {gpu.name: gpu for gpu in gpus}
        self.assertIn("Intel(R) UHD Graphics 630", by_name)
        self.assertIn("NVIDIA GeForce GTX 1050 Ti", by_name)
        self.assertEqual(by_name["Intel(R) UHD Graphics 630"].kind, "integrated")
        self.assertEqual(by_name["NVIDIA GeForce GTX 1050 Ti"].kind, "discrete")
        self.assertEqual(sum(1 for gpu in gpus if gpu.kind == "discrete"), 1)

    def test_options_offer_default_power_saving_high_performance(self) -> None:
        ids = {option.id for option in self.backend.list_options()}
        self.assertEqual(
            ids,
            {
                WINDOWS_OPTION_DEFAULT,
                WINDOWS_OPTION_POWER_SAVING,
                WINDOWS_OPTION_HIGH_PERFORMANCE,
            },
        )

    # Requirement 2 ---------------------------------------------------------
    def test_installed_browsers_detection(self) -> None:
        browsers = self.backend.list_browsers()
        names = sorted(browser.name for browser in browsers)
        self.assertEqual(
            names,
            ["Firefox Developer Edition", "Google Chrome", "Microsoft Edge", "Yandex"],
        )
        chrome = self.world.browser("Google Chrome")
        self.assertEqual(chrome.executable.lower(), CHROME_EXE.lower())
        self.assertEqual(chrome.id, "windows:google-chrome")
        self.assertTrue(all(browser.supported for browser in browsers))
        self.assertIn("registry", {browser.source for browser in browsers})
        self.assertNotIn("Internet Explorer", names)

    # Requirement 5 ---------------------------------------------------------
    def test_current_accelerator_reported_from_registry(self) -> None:
        default = self.backend.current_option(self.chrome)
        self.assertEqual(default.id, WINDOWS_OPTION_DEFAULT)

        self.world.registry.set_string(
            HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "GpuPreference=2;"
        )
        high = self.backend.current_option(self.chrome)
        self.assertEqual(high.id, WINDOWS_OPTION_HIGH_PERFORMANCE)
        self.assertIn("производительность", high.label.lower())

        self.world.registry.set_string(
            HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "AppStatus=0;GpuPreference=1;"
        )
        power = self.backend.current_option(self.chrome)
        self.assertEqual(power.id, WINDOWS_OPTION_POWER_SAVING)

        self.world.registry.set_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "GpuPreference=9;")
        unknown = self.backend.current_option(self.chrome)
        self.assertEqual(unknown.id, WINDOWS_OPTION_DEFAULT)

    # Requirements 7 + 8 ----------------------------------------------------
    def test_refuses_to_apply_while_browser_running(self) -> None:
        self.world.processes.paths = [CHROME_EXE]
        self.assertTrue(self.backend.is_browser_running(self.chrome))
        result = self.backend.apply(self.chrome, self.world.option(WINDOWS_OPTION_HIGH_PERFORMANCE))
        self.assertFalse(result.ok)
        self.assertIn("запущен", (result.message or "").lower() + (result.details or "").lower())
        self.assertEqual(self.world.registry.write_calls, [])
        self.assertEqual(self.world.state_entries(), {})

    def test_apply_writes_per_user_registry_no_admin(self) -> None:
        self.world.processes.paths = []
        result = self.backend.apply(self.chrome, self.world.option(WINDOWS_OPTION_HIGH_PERFORMANCE))
        self.assertTrue(result.ok, msg=str(result.message) + " / " + str(result.details))
        self.assertEqual(
            self.world.registry.write_calls,
            [(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "GpuPreference=2;")],
        )
        self.assertEqual(self.world.pref_value(), "GpuPreference=2;")
        self.assertIn("GpuPreference=2;", result.details or "")
        self.assertTrue(result.details)
        self.assertEqual(len(self.world.state_entries()), 1)
        pending = self.backend.pending_changes()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].browser_id, self.chrome.id)
        self.assertEqual(self.backend.current_option(self.chrome).id, WINDOWS_OPTION_HIGH_PERFORMANCE)

    def test_restore_all_with_no_changes_is_safe(self) -> None:
        result = self.backend.restore_all()
        self.assertTrue(result.ok)
        self.assertEqual(self.world.registry.delete_calls, [])

    # Undo correctness ------------------------------------------------------
    def test_second_apply_preserves_first_original_value(self) -> None:
        self.world.registry.set_string(
            HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "AppStatus=0;GpuPreference=1;"
        )
        registry = self.world.registry
        first = self.backend.apply(self.chrome, self.world.option(WINDOWS_OPTION_HIGH_PERFORMANCE))
        self.assertTrue(first.ok)
        self.assertEqual(self.world.pref_value(), "AppStatus=0;GpuPreference=2;")
        entries = self.world.state_entries()
        self.assertEqual(len(entries), 1)
        entry = next(iter(entries.values()))
        self.assertEqual(entry.get("original_data"), "AppStatus=0;GpuPreference=1;")
        self.assertTrue(entry.get("original_exists"))

        second = self.backend.apply(self.chrome, self.world.option(WINDOWS_OPTION_POWER_SAVING))
        self.assertTrue(second.ok)
        self.assertEqual(self.world.pref_value(), "AppStatus=0;GpuPreference=1;")
        entry_after_second = next(iter(self.world.state_entries().values()))
        self.assertEqual(
            entry_after_second.get("original_data"), "AppStatus=0;GpuPreference=1;"
        )
        self.assertEqual(len(self.world.state_entries()), 1)

        restored = self.backend.restore_all()
        self.assertTrue(restored.ok)
        self.assertEqual(self.world.pref_value(), "AppStatus=0;GpuPreference=1;")
        self.assertEqual(self.world.state_entries(), {})
        self.assertEqual(registry.delete_calls, [])

    def test_undo_removes_value_that_did_not_exist_before(self) -> None:
        self.assertIsNone(self.world.pref_value())
        applied = self.backend.apply(self.chrome, self.world.option(WINDOWS_OPTION_HIGH_PERFORMANCE))
        self.assertTrue(applied.ok)
        restored = self.backend.restore_all()
        self.assertTrue(restored.ok)
        self.assertIsNone(self.world.pref_value())
        self.assertEqual(
            self.world.registry.delete_calls,
            [(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE)],
        )
        self.assertEqual(self.world.state_entries(), {})

    def test_apply_survives_denied_registry_write(self) -> None:
        self.world.registry.write_error = PermissionError(13, "Access is denied")
        result = self.backend.apply(self.chrome, self.world.option(WINDOWS_OPTION_HIGH_PERFORMANCE))
        self.assertFalse(result.ok)
        self.assertIsNone(self.world.pref_value())
        self.assertEqual(self.world.state_entries(), {})

    # Requirement 9 launch button backend seam ------------------------------
    def test_launch_browser_only_when_closed(self) -> None:
        launched = self.backend.launch(self.chrome)
        self.assertTrue(launched.ok, msg=str(launched.message))
        self.assertEqual(self.world.system.launched, [[CHROME_EXE]])

        self.world.processes.paths = [CHROME_EXE]
        blocked = self.backend.launch(self.chrome)
        self.assertFalse(blocked.ok)
        self.assertEqual(self.world.system.launched, [[CHROME_EXE]])

    def test_state_is_platform_scoped(self) -> None:
        state = self.world.state
        state.put("linux:google-chrome", {"platform": LINUX, "option_id": LINUX_OPTION_NVIDIA_OFFLOAD})
        applied = self.backend.apply(self.chrome, self.world.option(WINDOWS_OPTION_HIGH_PERFORMANCE))
        self.assertTrue(applied.ok)
        self.assertEqual(len(self.backend.pending_changes()), 1)
        self.backend.restore_all()
        entries = self.world.state_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries["linux:google-chrome"]["platform"], LINUX)


# ---------------------------------------------------------------------------
# Linux fixture world (condensed from tests/test_linux.py).
# ---------------------------------------------------------------------------
GOOGLE_CHROME_DESKTOP = (
    "[Desktop Entry]\n"
    "Version=1.0\n"
    "Type=Application\n"
    "Name=Google Chrome\n"
    "GenericName=Web Browser\n"
    "Exec=/usr/bin/google-chrome-stable %U\n"
    "Terminal=false\n"
    "Icon=google-chrome\n"
    "Categories=Network;WebBrowser;\n"
    "MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;\n"
)
FIREFOX_DESKTOP = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=Firefox\n"
    "Exec=/usr/bin/firefox %u\n"
    "Categories=Network;WebBrowser;\n"
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def pci_dir_name(pci: str) -> str:
    return pci.replace(":", "_")


class FakeLinuxWorld:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.data_dir = root / "data"
        self.sysfs = root / "sys"
        self.proc = root / "proc"
        self.os_release = root / "etc" / "os-release"
        write_text(
            self.os_release,
            'PRETTY_NAME="Ubuntu 24.04 LTS"\nNAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\n',
        )
        self.apps = {
            "system": root / "usr/share/applications",
            "user": self.home / ".local/share/applications",
        }
        for path in self.apps.values():
            path.mkdir(parents=True, exist_ok=True)
        self.home.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sysfs.mkdir(parents=True, exist_ok=True)
        self.proc.mkdir(parents=True, exist_ok=True)
        self.executables: dict[str, str] = {}
        self.environ = {"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "GNOME"}
        self.state = StateStore(self.data_dir)

    def register_executable(self, path: str) -> None:
        self.executables[path] = path
        self.executables[os.path.basename(path)] = path

    def which(self, name: str):
        return self.executables.get(name)

    def backend(self, **overrides) -> LinuxBackend:
        kwargs = dict(
            home=self.home,
            data_dir=self.data_dir,
            state=self.state,
            sysfs_root=self.sysfs,
            proc_root=self.proc,
            desktop_dirs=[self.apps["system"], self.apps["user"]],
            applications_dir=self.apps["user"],
            which=self.which,
            os_release_path=self.os_release,
            environ=self.environ,
        )
        kwargs.update(overrides)
        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        return LinuxBackend(**kwargs)

    def add_gpu(
        self,
        card: str = "card0",
        pci: str = "0000:00:02.0",
        vendor: str = "0x8086",
        device: str = "0x9a49",
        driver: str = "i915",
        boot_vga: bool = False,
        vram_bytes: int | None = None,
        product_name: str | None = None,
    ) -> Path:
        device_dir = self.sysfs / "class" / "drm" / card / "device"
        device_dir.mkdir(parents=True, exist_ok=True)
        write_text(device_dir / "vendor", vendor + "\n")
        write_text(device_dir / "device", device + "\n")
        write_text(device_dir / "class", "0x030000\n")
        if boot_vga:
            write_text(device_dir / "boot_vga", "1\n")
        if vram_bytes is not None:
            write_text(device_dir / "mem_info_vram_total", str(vram_bytes) + "\n")
        if product_name:
            write_text(device_dir / "product_name", product_name + "\n")
        write_text(device_dir / "uevent", "DRIVER=" + driver + "\nPCI_SLOT_NAME=" + pci + "\n")
        write_text(device_dir / "driver", driver)
        alt_dir = self.sysfs / "bus" / "pci" / "devices" / pci_dir_name(pci)
        alt_dir.mkdir(parents=True, exist_ok=True)
        if alt_dir != device_dir:
            for name in ("vendor", "device", "class", "boot_vga", "mem_info_vram_total", "product_name"):
                source = device_dir / name
                if source.is_file():
                    write_text(alt_dir / name, source.read_text(encoding="utf-8"))
            write_text(alt_dir / "uevent", (device_dir / "uevent").read_text(encoding="utf-8"))
            write_text(alt_dir / "driver", driver)
        return device_dir

    def add_nvidia_info(self, pci: str, model: str) -> None:
        write_text(
            self.proc / "driver" / "nvidia" / "gpus" / pci_dir_name(pci) / "information",
            "Model:           " + model + "\nIRQ:             129\nGPU UUID:        GPU-1234\n",
        )

    def add_desktop(self, where: str, filename: str, text: str) -> Path:
        path = self.apps[where] / filename
        write_text(path, text)
        return path

    def add_process(self, pid: int, cmdline: list[str], comm: str | None = None) -> None:
        directory = self.proc / str(pid)
        directory.mkdir(parents=True, exist_ok=True)
        payload = b"\x00".join(part.encode("utf-8") for part in cmdline) + b"\x00"
        (directory / "cmdline").write_bytes(payload)
        write_text(directory / "comm", (comm or os.path.basename(cmdline[0])) + "\n")


def standard_linux_world(root: Path) -> FakeLinuxWorld:
    world = FakeLinuxWorld(root)
    world.add_gpu(card="card0", pci="0000:00:02.0", vendor="0x8086", device="0x9a49", driver="i915", boot_vga=True)
    world.add_gpu(
        card="card1",
        pci="0000:01:00.0",
        vendor="0x10de",
        device="0x1f82",
        driver="nvidia",
        vram_bytes=8 * 1024 ** 3,
    )
    world.add_nvidia_info("0000:01:00.0", "NVIDIA GeForce GTX 1650")
    world.register_executable("/usr/bin/google-chrome-stable")
    world.register_executable("/usr/bin/firefox")
    world.add_desktop("system", "google-chrome.desktop", GOOGLE_CHROME_DESKTOP)
    world.add_desktop("system", "firefox.desktop", FIREFOX_DESKTOP)
    return world


class LinuxBackendIntegrationTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.world = standard_linux_world(self.temp_dir("linux-world-"))
        self.backend = self.world.backend()
        self.chrome = self.linux_browser("Google Chrome")

    def linux_browser(self, name: str):
        for browser in self.backend.list_browsers():
            if browser.name == name:
                return browser
        raise AssertionError("browser not found: " + name)

    def chrome_override(self) -> Path:
        return self.backend._override_path(self.chrome.id)

    def data_files(self, suffix: str) -> list[Path]:
        return sorted(self.world.data_dir.rglob("*" + suffix))

    # Requirements 1 + 2 + 3 ------------------------------------------------
    def test_os_detection_from_os_release(self) -> None:
        info = self.backend.os_info()
        self.assertEqual(info.platform_key, LINUX)
        self.assertEqual(info.name, "Ubuntu 24.04 LTS")
        self.assertEqual(info.version, "24.04")
        self.assertEqual(info.session, "X11")

    def test_installed_browsers_detection(self) -> None:
        browsers = self.backend.list_browsers()
        names = sorted(browser.name for browser in browsers)
        self.assertIn("Google Chrome", names)
        self.assertIn("Firefox", names)
        chrome = self.linux_browser("Google Chrome")
        self.assertEqual(chrome.executable, "/usr/bin/google-chrome-stable")

    def test_graphics_chips_detection(self) -> None:
        gpus = self.backend.list_gpus()
        self.assertEqual(len(gpus), 2)
        kinds = sorted(gpu.kind for gpu in gpus)
        self.assertEqual(kinds, ["discrete", "integrated"])
        nvidia = next(gpu for gpu in gpus if gpu.vendor == "nvidia")
        self.assertIn("GTX 1650", nvidia.name)
        self.assertEqual(nvidia.memory_mb, 8192)

    def test_options_include_nvidia_offload(self) -> None:
        option_ids = {option.id for option in self.backend.list_options()}
        self.assertIn(LINUX_OPTION_DEFAULT, option_ids)
        self.assertIn(LINUX_OPTION_NVIDIA_OFFLOAD, option_ids)
        listed = {option.id: option for option in self.backend.list_options()}
        self.assertIn("NVIDIA", listed[LINUX_OPTION_NVIDIA_OFFLOAD].label)
        self.assertEqual(self.backend.current_option(self.chrome).id, LINUX_OPTION_DEFAULT)

    # Requirement 7 + 8 (per-user .desktop override, no root) ---------------
    def test_apply_writes_user_override_and_wrapper(self) -> None:
        system_desktop = self.world.apps["system"] / "google-chrome.desktop"
        original_text = system_desktop.read_text(encoding="utf-8")
        self.world.add_process(5000, ["/usr/bin/google-chrome-stable"])
        self.assertTrue(self.backend.is_browser_running(self.chrome))
        blocked = self.backend.apply(self.chrome, self.linux_option(LINUX_OPTION_NVIDIA_OFFLOAD))
        self.assertFalse(blocked.ok)
        self.assertIn("запущен", (blocked.message or "").lower() + (blocked.details or "").lower())
        self.assertFalse(self.chrome_override().exists())
        shutil.rmtree(self.world.proc / "5000")

        result = self.backend.apply(self.chrome, self.linux_option(LINUX_OPTION_NVIDIA_OFFLOAD))
        self.assertTrue(result.ok, msg=str(result.message) + " / " + str(result.details))
        self.assertEqual(system_desktop.read_text(encoding="utf-8"), original_text)

        override = self.chrome_override()
        self.assertTrue(override.is_file(), msg="override not written: " + str(override))
        override_text = override.read_text(encoding="utf-8")
        self.assertIn("[Desktop Entry]", override_text)
        self.assertIn("wrappers", override_text)
        self.assertIn("X-BrowserGpuSwitch-Mode=linux:nvidia-offload", override_text)
        self.assertIn("google-chrome-stable", override_text)

        wrappers = [path for path in self.data_files(".sh") if path.is_file()]
        self.assertTrue(wrappers, msg="wrapper script not created under " + str(self.world.data_dir))
        wrapper_texts = [path.read_text(encoding="utf-8") for path in wrappers]
        joined = "\n".join(wrapper_texts)
        self.assertIn("__NV_PRIME_RENDER_OFFLOAD=1", joined)
        self.assertIn("__GLX_VENDOR_LIBRARY_NAME=nvidia", joined)
        self.assertIn("/usr/bin/google-chrome-stable", joined)
        # Execute bit is verified statically below: Windows fixtures cannot store
        # POSIX permission bits, so a runtime chmod check is only meaningful on POSIX.
        linux_source = (WORKSPACE / "app" / "platforms" / "linux.py").read_text(encoding="utf-8")
        self.assertIn("_write_atomic(wrapper_path, script, 0o755)", linux_source)
        self.assertTrue(all(text.startswith("#!") for text in wrapper_texts), msg="wrapper is not a script")
        if os.name == "posix":
            for path in wrappers:
                mode = path.stat().st_mode
                self.assertTrue(mode & stat.S_IXUSR, msg="wrapper is not executable: " + str(path))

        backups = self.data_files("original.desktop")
        self.assertTrue(backups, msg="original desktop backup not stored")
        backup_texts = [path.read_text(encoding="utf-8") for path in backups]
        self.assertIn(original_text, backup_texts)

        entries = self.backend.state.load().get("entries") or {}
        self.assertEqual(len(entries), 1)
        entry = next(iter(entries.values()))
        self.assertEqual(entry.get("platform"), LINUX)
        self.assertTrue(entry.get("created_by_us"))
        pending = self.backend.pending_changes()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].browser_id, self.chrome.id)

    def test_undo_restores_original_and_removes_our_files(self) -> None:
        result = self.backend.apply(self.chrome, self.linux_option(LINUX_OPTION_NVIDIA_OFFLOAD))
        self.assertTrue(result.ok)
        self.assertTrue(self.chrome_override().exists())
        first_entry = next(iter((self.backend.state.load().get("entries") or {}).values()))
        original_exec = first_entry.get("original_exec")

        again = self.backend.apply(self.chrome, self.linux_option(LINUX_OPTION_NVIDIA_OFFLOAD))
        self.assertTrue(again.ok, msg="second apply must be allowed: " + str(again.message))
        second_entry = next(iter((self.backend.state.load().get("entries") or {}).values()))
        self.assertEqual(second_entry.get("original_exec"), original_exec)

        restored = self.backend.restore_all()
        self.assertTrue(restored.ok, msg=str(restored.message) + " / " + str(restored.details))
        self.assertFalse(self.chrome_override().exists(), msg="our override was not removed")
        self.assertEqual(self.data_files(".sh"), [], msg="wrapper was not removed")
        self.assertEqual(self.backend.state.load().get("entries"), {})
        self.assertEqual(self.backend.pending_changes(), [])

    def test_restore_all_without_changes_is_safe(self) -> None:
        result = self.backend.restore_all()
        self.assertTrue(result.ok)
        self.assertEqual(self.backend.state.load().get("entries"), {})
        self.assertEqual(self.data_files(".sh"), [])

    # Linux safety ----------------------------------------------------------
    def test_foreign_user_desktop_is_never_overwritten(self) -> None:
        foreign = "# my own override, not created by GPU Switch\n[Desktop Entry]\nType=Application\nName=Google Chrome\nExec=/usr/bin/google-chrome-stable --my-flag\n"
        override = self.chrome_override()
        write_text(override, foreign)
        result = self.backend.apply(self.chrome, self.linux_option(LINUX_OPTION_NVIDIA_OFFLOAD))
        self.assertFalse(result.ok)
        text = (result.message or "") + " " + (result.details or "")
        self.assertIn("не будем", text.lower())
        self.assertIn("Файл:", text)
        self.assertEqual(override.read_text(encoding="utf-8"), foreign)
        self.assertEqual(self.backend.state.load().get("entries"), {})

    def test_restore_keeps_foreign_file_but_removes_our_wrapper(self) -> None:
        applied = self.backend.apply(self.chrome, self.linux_option(LINUX_OPTION_NVIDIA_OFFLOAD))
        self.assertTrue(applied.ok)
        override = self.chrome_override()
        foreign = "# edited by another program\n[Desktop Entry]\nType=Application\nName=Google Chrome\nExec=/usr/bin/google-chrome-stable\n"
        write_text(override, foreign)
        restored = self.backend.restore_all()
        self.assertTrue(restored.ok, msg=str(restored.message) + " / " + str(restored.details))
        self.assertEqual(override.read_text(encoding="utf-8"), foreign)
        warnings = " ".join(restored.warnings or [])
        self.assertIn("изменён другой программой", warnings)
        self.assertEqual(self.data_files(".sh"), [], msg="our wrapper must still be removed")
        self.assertEqual(self.backend.state.load().get("entries"), {})

    def test_apply_default_undoes_override(self) -> None:
        self.assertTrue(
            self.backend.apply(self.chrome, self.linux_option(LINUX_OPTION_NVIDIA_OFFLOAD)).ok
        )
        self.assertTrue(self.chrome_override().exists())
        back = self.backend.apply(self.chrome, self.linux_option(LINUX_OPTION_DEFAULT))
        self.assertTrue(back.ok, msg=str(back.message) + " / " + str(back.details))
        self.assertFalse(self.chrome_override().exists())
        self.assertEqual(self.backend.current_option(self.chrome).id, LINUX_OPTION_DEFAULT)

    def linux_option(self, option_id: str):
        for option in self.backend.list_options():
            if option.id == option_id:
                return option
        raise AssertionError("linux option not found: " + option_id)


# ---------------------------------------------------------------------------
# StateStore persistence / corrupt state quarantine.
# ---------------------------------------------------------------------------
class StateStoreIntegrationTests(TempDirTestCase):
    def test_roundtrip_and_default_shape(self) -> None:
        state = StateStore(self.temp_dir("state-"))
        loaded = state.load()
        self.assertEqual(loaded.get("version"), 1)
        self.assertEqual(loaded.get("entries"), {})
        state.put("windows:google-chrome", {"platform": WINDOWS, "option_id": WINDOWS_OPTION_HIGH_PERFORMANCE})
        state2 = StateStore(state.data_dir)
        self.assertEqual(
            state2.get("windows:google-chrome"),
            {"platform": WINDOWS, "option_id": WINDOWS_OPTION_HIGH_PERFORMANCE},
        )

    def test_corrupt_json_is_quarantined_not_fatal(self) -> None:
        directory = self.temp_dir("state-")
        write_text(directory / "state.json", "{this is not json")
        state = StateStore(directory)
        loaded = state.load()
        self.assertEqual(loaded.get("version"), 1)
        self.assertEqual(loaded.get("entries"), {})
        quarantined = list(directory.glob("state.json.corrupt-*"))
        self.assertTrue(quarantined, msg="corrupt state was not quarantined")
        self.assertFalse((directory / "state.json").exists())
        state.put("linux:google-chrome", {"platform": LINUX})
        self.assertEqual(len(StateStore(directory).load().get("entries") or {}), 1)

    def test_non_object_entries_are_quarantined(self) -> None:
        directory = self.temp_dir("state-")
        (directory / "state.json").write_text('{"version": 1, "entries": []}', encoding="utf-8")
        loaded = StateStore(directory).load()
        self.assertEqual(loaded.get("entries"), {})
        self.assertTrue(list(directory.glob("state.json.corrupt-*")))


# ---------------------------------------------------------------------------
# GUI acceptance: drive the controller without a visible interactive session.
# ---------------------------------------------------------------------------
@unittest.skipUnless(TK_AVAILABLE, TEXT_NEEDS_TK)
class WindowsGuiAcceptanceTests(TempDirTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.world = FakeWindowsWorld(self.temp_dir("gui-state-"))
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = ui.GpuSwitchApp(self.root, self.world.backend)
        self.notifications: list[tuple[str, str]] = []
        self.app.confirm = lambda *args, **kwargs: True
        self.app.notify = lambda title, message: self.notifications.append((title, message))
        self.snapshot = self.app.refresh_now()
        self.root.update_idletasks()

    def tearDown(self) -> None:
        try:
            self.app.shutdown()
        finally:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
        super().tearDown()

    def select_chrome(self) -> None:
        self.assertTrue(self.app.select_browser_by_id("windows:google-chrome"))
        self.root.update_idletasks()

    # Requirement 4 ---------------------------------------------------------
    def test_browser_selection_window_and_prompt(self) -> None:
        self.assertEqual(self.root.title(), "GPU Switch")
        self.assertEqual(self.app.browser_prompt_label.cget("text"), ui.BROWSER_PROMPT)
        values = list(self.app.browser_combo.cget("values"))
        self.assertEqual(len(values), 4)
        self.assertTrue(any("Google Chrome" in value for value in values), msg=str(values))
        self.assertEqual(len(self.app.gpu_rows()), 2)
        self.assertEqual(len(self.app.option_labels()), 3)
        self.assertIn("Windows 11", self.app.system_label.cget("text"))
        self.assertFalse(self.app.running_warning_visible)

    # Requirement 5 ---------------------------------------------------------
    def test_current_accelerator_shown_after_selecting_browser(self) -> None:
        self.world.registry.set_string(
            HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "GpuPreference=2;"
        )
        self.app.refresh_now()
        self.select_chrome()
        text = self.app.current_label.cget("text")
        self.assertTrue(text.startswith("Сейчас включён ускоритель:"), msg=text)
        self.assertIn("Высокая производительность", text)

    # Requirement 6 ---------------------------------------------------------
    def test_user_can_choose_a_different_accelerator(self) -> None:
        self.select_chrome()
        self.assertTrue(self.app.select_option(WINDOWS_OPTION_POWER_SAVING))
        selected = self.app.selected_option()
        self.assertIsNotNone(selected)
        self.assertEqual(selected.id, WINDOWS_OPTION_POWER_SAVING)
        self.assertTrue(self.app.apply_enabled)

    # Requirement 7 ---------------------------------------------------------
    def test_running_browser_prompt_and_recheck(self) -> None:
        self.world.processes.paths = [CHROME_EXE]
        self.app.refresh_now()
        self.select_chrome()
        self.assertTrue(self.app.running_warning_visible)
        self.assertFalse(self.app.apply_enabled)
        blocked = self.app.apply_selected()
        self.assertIsNotNone(blocked)
        self.assertFalse(blocked.ok)
        self.assertIn("запущен", self.app.status_text.lower())

        self.world.processes.paths = []
        self.app.check_again()
        self.assertFalse(self.app.running_warning_visible)
        self.assertTrue(self.app.apply_enabled)
        self.assertIn("закрыт", self.app.status_text.lower())

    # Requirements 8 + 9 ----------------------------------------------------
    def test_apply_success_dialog_exact_text_and_launch_button(self) -> None:
        self.select_chrome()
        self.assertTrue(self.app.select_option(WINDOWS_OPTION_HIGH_PERFORMANCE))
        result = self.app.apply_selected()
        self.assertIsNotNone(result)
        self.assertTrue(result.ok, msg=str(result.message) + " / " + str(result.details))
        self.assertEqual(self.world.pref_value(), "GpuPreference=2;")
        self.assertTrue(self.app.ready_dialog_open())
        self.assertEqual(self.app.ready_dialog_title(), "Все настроено, запустите браузер")
        self.assertEqual(self.app.ready_dialog_message(), "Все настроено, запустите браузер")
        self.assertIn("Запустить браузер", self.widget_texts(self.app._ready_dialog))
        self.assertIn("Высокая производительность", self.widget_texts(self.app._ready_dialog))

        launch_button = self.find_button(self.app._ready_dialog, "Запустить браузер")
        self.assertIsNotNone(launch_button, msg="launch button missing")
        launch_button.invoke()
        self.root.update_idletasks()
        self.assertEqual(self.world.system.launched, [[CHROME_EXE]])
        self.assertTrue(any(title == "Запуск браузера" for title, _message in self.notifications))

    # Requirement 10 --------------------------------------------------------
    def test_restore_everything_button_is_always_available(self) -> None:
        self.assertFalse(self.app.restore_all_button.instate(["disabled"]))
        self.world.registry.set_string(
            HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "GpuPreference=1;"
        )
        self.app.refresh_now()
        self.select_chrome()
        self.assertTrue(self.app.select_option(WINDOWS_OPTION_HIGH_PERFORMANCE))
        self.assertTrue(self.app.apply_selected().ok)
        self.app.close_ready_dialog()
        self.assertFalse(self.app.restore_all_button.instate(["disabled"]))
        self.assertEqual(len(self.app.pending_rows()), 1)

        restored = self.app.restore_all()
        self.assertIsNotNone(restored)
        self.assertTrue(restored.ok, msg=str(restored.message))
        self.assertEqual(self.world.pref_value(), "GpuPreference=1;")
        self.assertEqual(self.world.state_entries(), {})
        self.assertTrue(self.app.pending_placeholder_visible())
        self.assertTrue(any(title == "Готово" for title, _message in self.notifications))

    # Requirement 10 (empty state) -----------------------------------------
    def test_restore_button_works_with_nothing_to_undo(self) -> None:
        self.assertFalse(self.app.restore_all_button.instate(["disabled"]))
        restored = self.app.restore_all()
        self.assertTrue(restored.ok)
        self.assertIn("Изменений не было", self.app.status_text)

    def test_shutdown_closes_backend_cleanly(self) -> None:
        self.app.shutdown()
        self.tear_down_shutdown_done = True
        self.assertTrue(self.app._shutdown_done)

    # helpers ---------------------------------------------------------------
    def widget_texts(self, widget) -> str:
        parts: list[str] = []
        try:
            text = widget.cget("text")
            if text:
                parts.append(str(text))
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            parts.append(self.widget_texts(child))
        return "\n".join(parts)

    def find_button(self, widget, label: str):
        try:
            if isinstance(widget, ttk.Button) and str(widget.cget("text")) == label:
                return widget
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            found = self.find_button(child, label)
            if found is not None:
                return found
        return None


if __name__ == "__main__":
    unittest.main()
