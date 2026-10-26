r"""Unit tests for the Windows backend (app/platforms/windows.py).

Every test runs against injected fakes: an in-memory registry, an in-memory
process provider, a fake system helper and a StateStore in a temporary
directory.  Nothing here reads or writes the real HKCU (writes are blocked in
the development sandbox, and tests must never depend on the host's settings).

Run from the repository root:

    C:\Python313\python.exe -m unittest discover -s tests -p "test_windows.py" -v
"""

from __future__ import annotations

import shutil
import struct
import sys
import unittest
import uuid
from pathlib import Path

from app.interface import (
    WINDOWS,
    WINDOWS_GPU_PREFS_KEY,
    WINDOWS_OPTION_DEFAULT,
    WINDOWS_OPTION_HIGH_PERFORMANCE,
    WINDOWS_OPTION_POWER_SAVING,
    Browser,
    GpuOption,
)
from app.platforms.windows import (
    GPU_CLASS_KEY,
    HKCU,
    HKLM,
    RunningProcess,
    WindowsBackend,
    WindowsRegistry,
    WindowsSystem,
    _command_executable,
    _compose_preference,
    _engine_for,
    _normcase,
    _parse_preference,
    _split_command,
)
from app.state import StateStore

WINDOWS_OR_LINUX = sys.platform.startswith("win")

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
FIREFOX_EXE = r"C:\Program Files\Firefox Developer Edition\firefox.exe"
YANDEX_EXE = r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe"
IE_EXE = r"C:\Program Files\Internet Explorer\iexplore.exe"

SAMPLE_EXISTING = (CHROME_EXE, EDGE_EXE, FIREFOX_EXE, YANDEX_EXE)

# The sandbox only allows writes inside the workspace, so all temporary
# StateStore directories live under tests/.tmp and are removed in tearDown.
TEST_TMP_ROOT = Path(__file__).resolve().parent / ".tmp"


def temp_state_dir(prefix="win-test-"):
    """Create a unique state directory inside the workspace.

    tempfile.mkdtemp() is avoided on purpose: in this Windows sandbox the
    directories it creates deny file writes (the sandbox only grants write
    access to plain directories created inside the workspace).
    """
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        candidate = TEST_TMP_ROOT / (prefix + uuid.uuid4().hex[:12])
        try:
            candidate.mkdir()
            return str(candidate)
        except FileExistsError:
            continue
    raise RuntimeError("не удалось создать временный каталог для тестов")

START_KEY = r"SOFTWARE\Clients\StartMenuInternet"
GPU_ROOT = GPU_CLASS_KEY


def _key_id(root, path):
    return (str(root).upper(), str(path).replace("/", "\\").strip("\\").lower())


class FakeRegistry:
    """In-memory stand-in for WindowsRegistry (same small public API)."""

    def __init__(self):
        self.available = True
        self.last_error = ""
        self.keys = {}
        self.write_calls = []
        self.delete_calls = []
        self.write_error = None
        self.delete_error = None

    # -- building helpers --------------------------------------------------
    def ensure_key(self, root, path):
        kid = _key_id(root, path)
        if kid not in self.keys:
            self.keys[kid] = {"values": {}, "subkeys": {}}
        return self.keys[kid]

    def add_key(self, root, path):
        self.ensure_key(root, path)
        return self

    def add_value(self, root, path, name, value, value_type=1):
        key = self.ensure_key(root, path)
        key["values"][str(name).lower()] = (str(name), value, int(value_type))
        return self

    def add_subkey(self, root, parent, child):
        key = self.ensure_key(root, parent)
        key["subkeys"][str(child).lower()] = str(child)
        child_path = str(parent).rstrip("\\") + "\\" + str(child)
        self.ensure_key(root, child_path)
        return self

    # -- WindowsRegistry API ----------------------------------------------
    def get_value(self, root, path, name=""):
        key = self.keys.get(_key_id(root, path))
        if not key:
            return None
        item = key["values"].get(str(name).lower())
        return None if item is None else item[1]

    def get_string(self, root, path, name=""):
        value = self.get_value(root, path, name)
        return None if value is None else str(value)

    def list_values(self, root, path):
        key = self.keys.get(_key_id(root, path))
        if not key:
            return []
        return list(key["values"].values())

    def list_subkeys(self, root, path):
        key = self.keys.get(_key_id(root, path))
        if not key:
            return []
        return list(key["subkeys"].values())

    def set_string(self, root, path, name, data):
        if self.write_error is not None:
            raise self.write_error
        key = self.ensure_key(root, path)
        self.write_calls.append((root, path, name, data))
        existing = key["values"].get(str(name).lower())
        real_name = existing[0] if existing else str(name)
        key["values"][str(name).lower()] = (real_name, str(data), 1)

    def delete_value(self, root, path, name):
        if self.delete_error is not None:
            raise self.delete_error
        key = self.keys.get(_key_id(root, path))
        if not key or str(name).lower() not in key["values"]:
            raise FileNotFoundError(str(name))
        del key["values"][str(name).lower()]
        self.delete_calls.append((root, path, name))


class FakeProcessProvider:
    """Process provider exposing only running_paths()/pids()."""

    def __init__(self, paths=(), pids=None):
        self.paths = list(paths)
        self._pids = list(pids) if pids else [1000 + index for index in range(len(paths))]
        self.last_error = ""

    def running_paths(self):
        return list(self.paths)

    def pids(self):
        return list(self._pids)


class ObjectProcessProvider:
    """Process provider exposing processes() with RunningProcess objects."""

    def __init__(self, entries=()):
        self.entries = list(entries)
        self.last_error = ""

    def processes(self):
        return list(self.entries)


class FakeSystem:
    """Fake WindowsSystem: file checks, OS version and detached launching."""

    def __init__(
        self,
        existing_paths=None,
        windows_version=(10, 0, 22631),
        architecture="AMD64",
        hostname="TEST-PC",
    ):
        self._existing = (
            None
            if existing_paths is None
            else {_normcase(str(path)) for path in existing_paths}
        )
        self._version = tuple(windows_version)
        self._architecture = str(architecture)
        self._hostname = str(hostname)
        self.launched = []
        self.launch_pid = 4242

    def windows_version(self):
        return self._version

    def architecture(self):
        return self._architecture

    def hostname(self):
        return self._hostname

    def file_exists(self, path):
        if not path:
            return False
        if self._existing is None:
            return True
        return _normcase(str(path)) in self._existing

    def launch(self, command):
        self.launched.append(list(command))
        return self.launch_pid


# ---------------------------------------------------------------------------
# Registry fixtures
# ---------------------------------------------------------------------------
def add_intel_gpu(registry, subkey="0000"):
    path = GPU_ROOT + "\\" + subkey
    registry.add_subkey(HKLM, GPU_ROOT, subkey)
    registry.add_value(HKLM, path, "DriverDesc", "Intel(R) UHD Graphics 630")
    registry.add_value(HKLM, path, "ProviderName", "Intel Corporation")
    registry.add_value(HKLM, path, "MatchingDeviceId", r"PCI\VEN_8086&DEV_3E9B")
    registry.add_value(HKLM, path, "DriverVersion", "31.0.101.2140")
    registry.add_value(
        HKLM,
        path,
        "HardwareInformation.MemorySize",
        struct.pack("<I", 0x40000000),
        3,
    )
    return path


def add_nvidia_gpu(registry, subkey="0001"):
    path = GPU_ROOT + "\\" + subkey
    registry.add_subkey(HKLM, GPU_ROOT, subkey)
    registry.add_value(HKLM, path, "DriverDesc", "NVIDIA GeForce GTX 1050 Ti")
    registry.add_value(HKLM, path, "ProviderName", "NVIDIA")
    registry.add_value(
        HKLM,
        path,
        "MatchingDeviceId",
        r"pci\ven_10de&dev_1c8c&subsys_12601025",
    )
    registry.add_value(HKLM, path, "DriverVersion", "32.0.15.8157")
    registry.add_value(HKLM, path, "HardwareInformation.qwMemorySize", 4294967296, 11)
    registry.add_value(HKLM, path, "ChipType", "GeForce GTX 1050 Ti")
    return path


def add_microsoft_gpu(registry, subkey="0002"):
    path = GPU_ROOT + "\\" + subkey
    registry.add_subkey(HKLM, GPU_ROOT, subkey)
    registry.add_value(HKLM, path, "DriverDesc", "Microsoft Basic Render Driver")
    registry.add_value(HKLM, path, "ProviderName", "Microsoft")
    registry.add_value(HKLM, path, "MatchingDeviceId", r"SWD\MSRRAS\MS_AGILEVPN")
    return path


def add_browser(registry, key_name, display, command_line, root=HKLM, parent=START_KEY):
    registry.add_subkey(root, parent, key_name)
    base = parent + "\\" + key_name
    registry.add_value(root, base, "", display)
    registry.add_value(root, base + r"\shell\open\command", "", command_line)
    return base


def sample_registry():
    registry = FakeRegistry()
    registry.add_value(HKLM, GPU_ROOT, "Class", "Display")
    add_intel_gpu(registry)
    add_nvidia_gpu(registry)
    registry.add_subkey(HKLM, GPU_ROOT, "Properties")

    add_browser(registry, "Google Chrome", "Google Chrome", '"' + CHROME_EXE + '"')
    add_browser(registry, "Microsoft Edge", "Microsoft Edge", '"' + EDGE_EXE + '"')
    add_browser(
        registry,
        "Firefox-CA9422711AE1A81C",
        "Firefox Developer Edition",
        '"' + FIREFOX_EXE + '"',
    )
    add_browser(registry, "Yandex", "Yandex", '"' + YANDEX_EXE + '"')
    add_browser(registry, "IEXPLORE.EXE", "Internet Explorer", IE_EXE)
    return registry


def preference_key(registry):
    registry.add_key(HKCU, WINDOWS_GPU_PREFS_KEY)
    return registry


# ---------------------------------------------------------------------------
# Base test case
# ---------------------------------------------------------------------------
class BackendTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = temp_state_dir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def make_backend(
        self,
        registry=None,
        processes=None,
        system=None,
        state_dir=None,
        state=None,
    ):
        registry = sample_registry() if registry is None else registry
        processes = FakeProcessProvider() if processes is None else processes
        system = (
            FakeSystem(existing_paths=SAMPLE_EXISTING) if system is None else system
        )
        if state is None:
            state = StateStore(state_dir or self.tmpdir)
        backend = WindowsBackend(
            registry=registry,
            process_provider=processes,
            state=state,
            system=system,
        )
        return backend

    @staticmethod
    def option(backend, option_id):
        for item in backend.list_options():
            if item.id == option_id:
                return item
        raise AssertionError("option not found: " + option_id)

    @staticmethod
    def browser(backend, name):
        for item in backend.list_browsers():
            if item.name == name:
                return item
        raise AssertionError("browser not found: " + name)

    def chrome_browser(self):
        return Browser(
            id="windows:google-chrome",
            name="Google Chrome",
            executable=CHROME_EXE,
            launch_command=(CHROME_EXE,),
            engine="chromium",
            process_names=("chrome.exe",),
            source="registry",
        )


# ---------------------------------------------------------------------------
# Module / platform basics
# ---------------------------------------------------------------------------
class PlatformBasicsTests(BackendTestCase):
    def test_platform_key_is_windows(self):
        backend = self.make_backend()
        self.assertEqual(backend.platform_key, WINDOWS)
        self.assertEqual(WINDOWS, "windows")

    def test_constructor_accepts_only_collaborators(self):
        backend = WindowsBackend(
            registry=FakeRegistry(),
            process_provider=FakeProcessProvider(),
            state=StateStore(self.tmpdir),
            system=FakeSystem(),
        )
        self.assertIsInstance(backend.diagnostics(), str)

    def test_close_returns_none(self):
        backend = self.make_backend()
        self.assertIsNone(backend.close())

    def test_os_info_windows_11(self):
        backend = self.make_backend(
            system=FakeSystem(existing_paths=SAMPLE_EXISTING, windows_version=(10, 0, 22631))
        )
        info = backend.os_info()
        self.assertEqual(info.platform_key, WINDOWS)
        self.assertEqual(info.name, "Windows 11")
        self.assertEqual(info.version, "10.0.22631")
        self.assertEqual(info.arch, "AMD64")
        self.assertEqual(info.hostname, "TEST-PC")
        self.assertIn("Windows 11", info.pretty)

    def test_os_info_windows_10(self):
        backend = self.make_backend(
            system=FakeSystem(existing_paths=SAMPLE_EXISTING, windows_version=(10, 0, 19045))
        )
        self.assertEqual(backend.os_info().name, "Windows 10")

    def test_now_iso_is_used_for_applied_at(self):
        backend = self.make_backend()
        result = backend.apply(
            self.chrome_browser(), self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE)
        )
        self.assertTrue(result.ok)
        change = backend.pending_changes()[0]
        self.assertIn("T", change.applied_at)


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------
class GpuDetectionTests(BackendTestCase):
    def test_lists_two_gpus_integrated_first(self):
        backend = self.make_backend()
        gpus = backend.list_gpus()
        self.assertEqual(len(gpus), 2)
        self.assertEqual(gpus[0].name, "Intel(R) UHD Graphics 630")
        self.assertEqual(gpus[0].vendor, "intel")
        self.assertEqual(gpus[0].kind, "integrated")
        self.assertEqual(gpus[0].driver, "31.0.101.2140")
        self.assertEqual(gpus[0].memory_mb, 1024)
        self.assertEqual(gpus[1].name, "NVIDIA GeForce GTX 1050 Ti")
        self.assertEqual(gpus[1].vendor, "nvidia")
        self.assertEqual(gpus[1].kind, "discrete")
        self.assertEqual(gpus[1].memory_mb, 4096)
        self.assertEqual(gpus[1].driver, "32.0.15.8157")

    def test_gpu_ids_include_pci_ids(self):
        backend = self.make_backend()
        ids = [gpu.id for gpu in backend.list_gpus()]
        self.assertIn("windows:gpu:8086:3e9b", ids)
        self.assertIn("windows:gpu:10de:1c8c", ids)

    def test_pci_address_is_uppercased(self):
        backend = self.make_backend()
        nvidia = backend.list_gpus()[1]
        self.assertEqual(nvidia.pci_address, r"PCI\VEN_10DE&DEV_1C8C")

    def test_skips_non_display_class_root(self):
        registry = FakeRegistry()
        registry.add_value(HKLM, GPU_ROOT, "Class", "Net")
        add_intel_gpu(registry)
        backend = self.make_backend(registry=registry)
        self.assertEqual(backend.list_gpus(), [])

    def test_empty_registry_yields_no_gpus(self):
        backend = self.make_backend(registry=FakeRegistry())
        self.assertEqual(backend.list_gpus(), [])

    def test_microsoft_basic_render_is_virtual(self):
        registry = sample_registry()
        add_microsoft_gpu(registry)
        backend = self.make_backend(registry=registry)
        gpus = backend.list_gpus()
        self.assertEqual(len(gpus), 3)
        virtual = gpus[-1]
        self.assertEqual(virtual.name, "Microsoft Basic Render Driver")
        self.assertEqual(virtual.vendor, "microsoft")
        self.assertEqual(virtual.kind, "virtual")

    def test_unknown_vendor_sorted_last(self):
        registry = sample_registry()
        path = GPU_ROOT + "\\" + "0005"
        registry.add_subkey(HKLM, GPU_ROOT, "0005")
        registry.add_value(HKLM, path, "DriverDesc", "Mystery Display Adapter")
        registry.add_value(HKLM, path, "ProviderName", "Acme Displays")
        registry.add_value(HKLM, path, "MatchingDeviceId", r"PCI\VEN_9999&DEV_0001")
        backend = self.make_backend(registry=registry)
        gpus = backend.list_gpus()
        self.assertEqual(gpus[-1].vendor, "other")
        self.assertEqual(gpus[-1].kind, "unknown")

    def test_subkey_with_other_class_value_is_skipped(self):
        registry = sample_registry()
        path = GPU_ROOT + "\\" + "0009"
        registry.add_subkey(HKLM, GPU_ROOT, "0009")
        registry.add_value(HKLM, path, "Class", "Net")
        registry.add_value(HKLM, path, "DriverDesc", "Network Adapter")
        backend = self.make_backend(registry=registry)
        self.assertEqual(len(backend.list_gpus()), 2)


# ---------------------------------------------------------------------------
# Browser detection
# ---------------------------------------------------------------------------
class BrowserDetectionTests(BackendTestCase):
    def test_lists_installed_browsers_sorted(self):
        backend = self.make_backend()
        browsers = backend.list_browsers()
        names = [browser.name for browser in browsers]
        self.assertEqual(
            names,
            ["Firefox Developer Edition", "Google Chrome", "Microsoft Edge", "Yandex"],
        )

    def test_chrome_fields(self):
        backend = self.make_backend()
        chrome = self.browser(backend, "Google Chrome")
        self.assertEqual(chrome.executable, CHROME_EXE)
        self.assertEqual(chrome.engine, "chromium")
        self.assertEqual(chrome.process_names, ("chrome.exe",))
        self.assertEqual(chrome.source, "registry")
        self.assertTrue(chrome.supported)

    def test_engine_mapping(self):
        backend = self.make_backend()
        self.assertEqual(self.browser(backend, "Google Chrome").engine, "chromium")
        self.assertEqual(self.browser(backend, "Microsoft Edge").engine, "chromium")
        self.assertEqual(
            self.browser(backend, "Firefox Developer Edition").engine, "gecko"
        )

    def test_internet_explorer_excluded(self):
        backend = self.make_backend()
        executables = [browser.executable for browser in backend.list_browsers()]
        self.assertNotIn(IE_EXE, executables)
        self.assertFalse(any("iexplore" in exe.lower() for exe in executables))

    def test_browser_with_missing_executable_is_skipped(self):
        registry = sample_registry()
        backend = self.make_backend(
            registry=registry,
            system=FakeSystem(existing_paths=(CHROME_EXE, EDGE_EXE, FIREFOX_EXE)),
        )
        names = [browser.name for browser in backend.list_browsers()]
        self.assertNotIn("Yandex", names)
        self.assertIn("Google Chrome", names)

    def test_duplicate_executable_deduped(self):
        registry = sample_registry()
        add_browser(
            registry,
            "Google Chrome (x86)",
            "Google Chrome (x86)",
            '"' + CHROME_EXE + '"',
            root=HKLM,
            parent=r"SOFTWARE\WOW6432Node\Clients\StartMenuInternet",
        )
        backend = self.make_backend(registry=registry)
        browsers = backend.list_browsers()
        chrome_paths = [
            browser for browser in browsers if _normcase(browser.executable) == _normcase(CHROME_EXE)
        ]
        self.assertEqual(len(chrome_paths), 1)

    def test_display_name_from_default_value(self):
        registry = sample_registry()
        backend = self.make_backend(registry=registry)
        yandex = self.browser(backend, "Yandex")
        self.assertEqual(yandex.executable, YANDEX_EXE)
        self.assertEqual(yandex.id, "windows:yandex")

    def test_fallback_to_well_known_paths(self):
        chrome_path = CHROME_EXE
        backend = self.make_backend(
            registry=FakeRegistry(),
            system=FakeSystem(existing_paths=(chrome_path,)),
        )
        browsers = backend.list_browsers()
        self.assertEqual(len(browsers), 1)
        self.assertEqual(browsers[0].name, "Google Chrome")
        self.assertEqual(browsers[0].source, "well-known")
        self.assertEqual(browsers[0].id, "windows:chrome")
        self.assertEqual(browsers[0].engine, "chromium")

    def test_command_with_arguments_is_preserved_in_launch_command(self):
        registry = sample_registry()
        add_browser(
            registry,
            "Google Chrome",
            "Google Chrome",
            '"' + CHROME_EXE + '" --profile-directory="Default"',
        )
        backend = self.make_backend(registry=registry)
        chrome = self.browser(backend, "Google Chrome")
        self.assertEqual(chrome.launch_command[0], CHROME_EXE)
        self.assertIn("--profile-directory", " ".join(chrome.launch_command))

    def test_shell_command_helpers(self):
        self.assertEqual(
            _command_executable('"C:\\Program Files\\App\\app.exe" --flag'),
            r"C:\Program Files\App\app.exe",
        )
        self.assertEqual(
            _command_executable(r"C:\Program Files\App\app.exe --flag"),
            r"C:\Program Files\App\app.exe",
        )
        self.assertEqual(
            _split_command('"C:\\Program Files\\App\\app.exe" --flag'),
            [r"C:\Program Files\App\app.exe", "--flag"],
        )
        self.assertEqual(_engine_for("chrome.exe", "Google Chrome"), "chromium")
        self.assertEqual(_engine_for("firefox.exe", "Firefox"), "gecko")


# ---------------------------------------------------------------------------
# Options / current option
# ---------------------------------------------------------------------------
class OptionsTests(BackendTestCase):
    def test_three_options_with_russian_chip_names(self):
        backend = self.make_backend()
        options = backend.list_options()
        self.assertEqual(
            [option.id for option in options],
            [
                WINDOWS_OPTION_DEFAULT,
                WINDOWS_OPTION_POWER_SAVING,
                WINDOWS_OPTION_HIGH_PERFORMANCE,
            ],
        )
        self.assertIn("По умолчанию", options[0].label)
        self.assertIn("Intel(R) UHD Graphics 630", options[1].label)
        self.assertIn("NVIDIA GeForce GTX 1050 Ti", options[2].label)
        self.assertEqual(options[1].payload["preference"], 1)
        self.assertEqual(options[2].payload["preference"], 2)
        self.assertEqual(options[0].kind, "auto")
        self.assertEqual(options[1].kind, "integrated")
        self.assertEqual(options[2].kind, "discrete")

    def test_options_without_gpus_use_generic_labels(self):
        backend = self.make_backend(registry=FakeRegistry())
        options = backend.list_options()
        self.assertEqual(len(options), 3)
        self.assertEqual(options[1].payload["preference"], 1)
        self.assertIn("Энергосбережение", options[1].label)
        self.assertIn("Высокая производительность", options[2].label)

    def test_current_option_default_when_no_value(self):
        backend = self.make_backend()
        current = backend.current_option(self.chrome_browser())
        self.assertEqual(current.id, WINDOWS_OPTION_DEFAULT)

    def test_current_option_high_performance(self):
        registry = preference_key(sample_registry())
        registry.add_value(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "GpuPreference=2;")
        backend = self.make_backend(registry=registry)
        current = backend.current_option(self.chrome_browser())
        self.assertEqual(current.id, WINDOWS_OPTION_HIGH_PERFORMANCE)

    def test_current_option_power_saving_with_other_fields(self):
        registry = preference_key(sample_registry())
        registry.add_value(
            HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "AppStatus=0;GpuPreference=1;"
        )
        backend = self.make_backend(registry=registry)
        current = backend.current_option(self.chrome_browser())
        self.assertEqual(current.id, WINDOWS_OPTION_POWER_SAVING)

    def test_current_option_unknown_preference_falls_back_to_default(self):
        registry = preference_key(sample_registry())
        registry.add_value(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "GpuPreference=7;")
        backend = self.make_backend(registry=registry)
        self.assertEqual(
            backend.current_option(self.chrome_browser()).id, WINDOWS_OPTION_DEFAULT
        )

    def test_current_option_is_case_insensitive(self):
        registry = preference_key(sample_registry())
        registry.add_value(
            HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE.upper(), "GpuPreference=2;"
        )
        backend = self.make_backend(registry=registry)
        self.assertEqual(
            backend.current_option(self.chrome_browser()).id,
            WINDOWS_OPTION_HIGH_PERFORMANCE,
        )

    def test_current_option_for_empty_browser(self):
        backend = self.make_backend()
        empty = Browser(id="windows:empty", name="Пусто", executable="")
        self.assertEqual(
            backend.current_option(empty).id, WINDOWS_OPTION_DEFAULT
        )

    def test_preference_helpers(self):
        self.assertEqual(_parse_preference("GpuPreference=2;"), 2)
        self.assertEqual(_parse_preference("AppStatus=0; GpuPreference=1;"), 1)
        self.assertIsNone(_parse_preference("AppStatus=0;"))
        self.assertEqual(_compose_preference("", 2), "GpuPreference=2;")
        self.assertEqual(
            _compose_preference("AppStatus=0;GpuPreference=2;", 1),
            "AppStatus=0;GpuPreference=1;",
        )
        self.assertEqual(
            _compose_preference("AppStatus=0;", 1), "AppStatus=0;GpuPreference=1;"
        )


# ---------------------------------------------------------------------------
# Process detection
# ---------------------------------------------------------------------------
class ProcessDetectionTests(BackendTestCase):
    def test_browser_running_by_full_path(self):
        backend = self.make_backend(
            processes=FakeProcessProvider(paths=[CHROME_EXE], pids=[321])
        )
        chrome = self.chrome_browser()
        self.assertTrue(backend.is_browser_running(chrome))
        self.assertEqual(backend.running_pids(chrome), [321])

    def test_browser_running_by_basename_only(self):
        backend = self.make_backend(
            processes=ObjectProcessProvider(
                entries=[RunningProcess(pid=55, path="", name="chrome.exe")]
            )
        )
        self.assertTrue(backend.is_browser_running(self.chrome_browser()))

    def test_other_browser_not_running(self):
        backend = self.make_backend(
            processes=FakeProcessProvider(paths=[CHROME_EXE], pids=[321])
        )
        edge = self.browser(backend, "Microsoft Edge")
        self.assertFalse(backend.is_browser_running(edge))
        self.assertEqual(backend.running_pids(edge), [])

    def test_running_check_is_case_insensitive(self):
        backend = self.make_backend(
            processes=FakeProcessProvider(paths=[CHROME_EXE.upper()], pids=[77])
        )
        self.assertTrue(backend.is_browser_running(self.chrome_browser()))

    def test_process_provider_failure_never_raises(self):
        class BrokenProvider:
            last_error = "boom"

            def running_paths(self):
                raise RuntimeError("snapshot failed")

            def pids(self):
                raise RuntimeError("snapshot failed")

        backend = self.make_backend(processes=BrokenProvider())
        self.assertFalse(backend.is_browser_running(self.chrome_browser()))
        self.assertEqual(backend.running_pids(self.chrome_browser()), [])

    def test_browser_without_executable_is_never_running(self):
        backend = self.make_backend()
        empty = Browser(id="windows:empty", name="Пусто", executable="")
        self.assertFalse(backend.is_browser_running(empty))


# ---------------------------------------------------------------------------
# Applying the preference
# ---------------------------------------------------------------------------
class ApplyTests(BackendTestCase):
    def test_apply_high_performance_creates_registry_value(self):
        registry = preference_key(sample_registry())
        backend = self.make_backend(registry=registry)
        chrome = self.chrome_browser()
        result = backend.apply(
            chrome, self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE)
        )
        self.assertTrue(result.ok, result.message)
        self.assertIn("Готово", result.message)
        self.assertIn("NVIDIA", result.message)
        value = registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE)
        self.assertEqual(value, "GpuPreference=2;")
        changes = backend.pending_changes()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].platform, WINDOWS)
        self.assertEqual(changes[0].browser_id, chrome.id)
        self.assertEqual(
            changes[0].option_id, WINDOWS_OPTION_HIGH_PERFORMANCE
        )
        self.assertIn("Google Chrome", changes[0].description)

    def test_apply_preserves_unknown_fields(self):
        registry = preference_key(sample_registry())
        registry.add_value(
            HKCU,
            WINDOWS_GPU_PREFS_KEY,
            CHROME_EXE,
            "AppStatus=0;GpuPreference=2;SomeFlag=1;",
        )
        backend = self.make_backend(registry=registry)
        backend.apply(
            self.chrome_browser(), self.option(backend, WINDOWS_OPTION_POWER_SAVING)
        )
        self.assertEqual(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE),
            "AppStatus=0;GpuPreference=1;SomeFlag=1;",
        )

    def test_apply_refuses_while_browser_running(self):
        registry = preference_key(sample_registry())
        backend = self.make_backend(
            registry=registry,
            processes=FakeProcessProvider(paths=[CHROME_EXE], pids=[10]),
        )
        result = backend.apply(
            self.chrome_browser(), self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE)
        )
        self.assertFalse(result.ok)
        self.assertIn("запущен", result.message)
        self.assertIsNone(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE)
        )
        self.assertEqual(backend.pending_changes(), [])

    def test_apply_refuses_unknown_option(self):
        backend = self.make_backend()
        result = backend.apply(
            self.chrome_browser(),
            GpuOption(id="windows:unknown", label="Что-то", payload={}),
        )
        self.assertFalse(result.ok)
        self.assertIn("Неизвестный", result.message)

    def test_apply_refuses_browser_without_executable(self):
        backend = self.make_backend()
        result = backend.apply(
            Browser(id="windows:empty", name="Пусто", executable=""),
            self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE),
        )
        self.assertFalse(result.ok)
        self.assertIn("путь", result.message)

    def test_apply_reports_registry_write_failure(self):
        registry = preference_key(sample_registry())
        registry.write_error = PermissionError(13, "Access is denied")
        backend = self.make_backend(registry=registry)
        result = backend.apply(
            self.chrome_browser(), self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE)
        )
        self.assertFalse(result.ok)
        self.assertIn("Не удалось сохранить", result.message)
        self.assertEqual(backend.pending_changes(), [])

    def test_apply_default_when_nothing_set(self):
        registry = preference_key(sample_registry())
        backend = self.make_backend(registry=registry)
        result = backend.apply(
            self.chrome_browser(), self.option(backend, WINDOWS_OPTION_DEFAULT)
        )
        self.assertTrue(result.ok)
        self.assertIn("уже действуют", result.message)
        self.assertEqual(backend.pending_changes(), [])

    def test_apply_default_restores_original_instead_of_writing_zero(self):
        registry = preference_key(sample_registry())
        registry.add_value(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "GpuPreference=1;")
        backend = self.make_backend(registry=registry)
        chrome = self.chrome_browser()
        backend.apply(chrome, self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE))
        result = backend.apply(chrome, self.option(backend, WINDOWS_OPTION_DEFAULT))
        self.assertTrue(result.ok)
        self.assertEqual(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE),
            "GpuPreference=1;",
        )
        self.assertEqual(backend.pending_changes(), [])

    def test_double_apply_keeps_first_original(self):
        registry = preference_key(sample_registry())
        backend = self.make_backend(registry=registry)
        chrome = self.chrome_browser()
        high = self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE)
        power = self.option(backend, WINDOWS_OPTION_POWER_SAVING)
        self.assertTrue(backend.apply(chrome, high).ok)
        self.assertTrue(backend.apply(chrome, power).ok)
        entry = backend._state.get(backend._state_key(chrome))
        self.assertIsNotNone(entry)
        self.assertFalse(entry["original_exists"])
        self.assertEqual(entry["original_data"], "")
        self.assertEqual(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE),
            "GpuPreference=1;",
        )
        self.assertEqual(len(backend.pending_changes()), 1)
        restore = backend.restore_all()
        self.assertTrue(restore.ok, restore.message)
        self.assertIsNone(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE)
        )

    def test_second_apply_keeps_original_data(self):
        registry = preference_key(sample_registry())
        registry.add_value(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, "GpuPreference=0;")
        backend = self.make_backend(registry=registry)
        chrome = self.chrome_browser()
        backend.apply(chrome, self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE))
        backend.apply(chrome, self.option(backend, WINDOWS_OPTION_POWER_SAVING))
        entry = backend._state.get(backend._state_key(chrome))
        self.assertTrue(entry["original_exists"])
        self.assertEqual(entry["original_data"], "GpuPreference=0;")
        backend.restore_all()
        self.assertEqual(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE),
            "GpuPreference=0;",
        )

    def test_apply_second_browser_independent(self):
        registry = preference_key(sample_registry())
        backend = self.make_backend(registry=registry)
        chrome = self.chrome_browser()
        edge = Browser(
            id="windows:microsoft-edge",
            name="Microsoft Edge",
            executable=EDGE_EXE,
            launch_command=(EDGE_EXE,),
            process_names=("msedge.exe",),
        )
        self.assertTrue(
            backend.apply(
                chrome, self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE)
            ).ok
        )
        self.assertTrue(
            backend.apply(edge, self.option(backend, WINDOWS_OPTION_POWER_SAVING)).ok
        )
        self.assertEqual(len(backend.pending_changes()), 2)
        self.assertEqual(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE),
            "GpuPreference=2;",
        )
        self.assertEqual(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, EDGE_EXE),
            "GpuPreference=1;",
        )


# ---------------------------------------------------------------------------
# Undo / restore
# ---------------------------------------------------------------------------
class RestoreTests(BackendTestCase):
    def test_restore_deletes_value_that_did_not_exist(self):
        registry = preference_key(sample_registry())
        backend = self.make_backend(registry=registry)
        chrome = self.chrome_browser()
        backend.apply(chrome, self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE))
        self.assertIsNotNone(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE)
        )
        result = backend.restore_all()
        self.assertTrue(result.ok, result.message)
        self.assertIn("Google Chrome", result.message)
        self.assertIsNone(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE)
        )
        self.assertEqual(backend.pending_changes(), [])

    def test_restore_writes_back_original_data(self):
        registry = preference_key(sample_registry())
        original = "AppStatus=0;GpuPreference=0;"
        registry.add_value(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE, original)
        backend = self.make_backend(registry=registry)
        chrome = self.chrome_browser()
        backend.apply(chrome, self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE))
        result = backend.restore_browser(chrome)
        self.assertTrue(result.ok, result.message)
        self.assertIn("возвращены", result.message)
        self.assertEqual(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE), original
        )
        self.assertEqual(backend.pending_changes(), [])

    def test_restore_all_without_changes_is_success(self):
        backend = self.make_backend()
        result = backend.restore_all()
        self.assertTrue(result.ok)
        self.assertIn("нечего", result.message)

    def test_restore_browser_without_changes_is_success(self):
        backend = self.make_backend()
        result = backend.restore_browser(self.chrome_browser())
        self.assertTrue(result.ok)
        self.assertIn("нет сохранённых изменений", result.message)

    def test_restore_ignores_other_platform_entries(self):
        registry = preference_key(sample_registry())
        state = StateStore(self.tmpdir)
        state.put(
            "linux:/usr/bin/firefox",
            {"platform": "linux", "browser_name": "Firefox", "applied_at": "2024-01-01T00:00:00+00:00"},
        )
        backend = self.make_backend(registry=registry, state=state)
        self.assertEqual(backend.pending_changes(), [])
        result = backend.restore_all()
        self.assertTrue(result.ok)
        self.assertIn("нечего", result.message)
        self.assertIn("linux:/usr/bin/firefox", state.keys())

    def test_restore_reports_registry_failure(self):
        registry = preference_key(sample_registry())
        registry.delete_error = PermissionError(13, "Access is denied")
        backend = self.make_backend(registry=registry)
        chrome = self.chrome_browser()
        backend.apply(chrome, self.option(backend, WINDOWS_OPTION_HIGH_PERFORMANCE))
        result = backend.restore_all()
        self.assertFalse(result.ok)
        self.assertIn("Не удалось", result.message)

    def test_state_persists_across_backend_instances(self):
        registry = preference_key(sample_registry())
        first = self.make_backend(registry=registry)
        chrome = self.chrome_browser()
        self.assertTrue(
            first.apply(
                chrome, self.option(first, WINDOWS_OPTION_HIGH_PERFORMANCE)
            ).ok
        )

        second = WindowsBackend(
            registry=registry,
            process_provider=FakeProcessProvider(),
            state=StateStore(self.tmpdir),
            system=FakeSystem(existing_paths=SAMPLE_EXISTING),
        )
        changes = second.pending_changes()
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].browser_name, "Google Chrome")
        result = second.restore_all()
        self.assertTrue(result.ok, result.message)
        self.assertIsNone(
            registry.get_string(HKCU, WINDOWS_GPU_PREFS_KEY, CHROME_EXE)
        )
        self.assertEqual(first.pending_changes(), [])

    def test_state_key_format(self):
        backend = self.make_backend()
        key = backend._state_key(self.chrome_browser())
        self.assertTrue(key.startswith("windows:"))
        self.assertEqual(key, "windows:" + CHROME_EXE.lower())


# ---------------------------------------------------------------------------
# Launch, notes, diagnostics
# ---------------------------------------------------------------------------
class LaunchTests(BackendTestCase):
    def test_launch_calls_system_with_executable(self):
        system = FakeSystem(existing_paths=SAMPLE_EXISTING)
        backend = self.make_backend(system=system)
        chrome = self.chrome_browser()
        result = backend.launch(chrome)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.pid, 4242)
        self.assertEqual(len(system.launched), 1)
        self.assertEqual(system.launched[0][0], CHROME_EXE)
        self.assertIn("Запускаю", result.message)

    def test_launch_drops_argument_placeholders(self):
        system = FakeSystem(existing_paths=SAMPLE_EXISTING)
        backend = self.make_backend(system=system)
        browser = Browser(
            id="windows:test",
            name="Тестовый браузер",
            executable=CHROME_EXE,
            launch_command=(CHROME_EXE, "%1"),
        )
        result = backend.launch(browser)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(system.launched[0], [CHROME_EXE])

    def test_launch_refuses_missing_executable(self):
        system = FakeSystem(existing_paths=())
        backend = self.make_backend(system=system)
        result = backend.launch(self.chrome_browser())
        self.assertFalse(result.ok)
        self.assertIn("найти", result.message)
        self.assertEqual(system.launched, [])

    def test_launch_refuses_while_running(self):
        system = FakeSystem(existing_paths=SAMPLE_EXISTING)
        backend = self.make_backend(
            system=system,
            processes=FakeProcessProvider(paths=[CHROME_EXE], pids=[9]),
        )
        result = backend.launch(self.chrome_browser())
        self.assertFalse(result.ok)
        self.assertIn("уже запущен", result.message)
        self.assertEqual(system.launched, [])

    def test_launch_without_command_fails_cleanly(self):
        backend = self.make_backend()
        broken = Browser(id="windows:broken", name="Сломанный", executable="")
        result = backend.launch(broken)
        self.assertFalse(result.ok)
        self.assertTrue(result.message)


class NotesAndDiagnosticsTests(BackendTestCase):
    def test_notes_are_russian(self):
        backend = self.make_backend()
        notes = backend.notes()
        self.assertGreaterEqual(len(notes), 2)
        joined = " ".join(notes)
        self.assertIn("запуска", joined.lower())
        self.assertIn("Windows", joined)

    def test_diagnostics_contains_sections(self):
        backend = self.make_backend()
        text = backend.diagnostics()
        self.assertIn("Backend: WindowsBackend", text)
        self.assertIn("Windows:", text)
        self.assertIn("GPUs:", text)
        self.assertIn("Browsers:", text)
        self.assertIn("Options:", text)
        self.assertIn("Pending changes:", text)
        self.assertIn("Intel(R) UHD Graphics 630", text)

    def test_diagnostics_survives_broken_registry(self):
        class ExplodingRegistry:
            available = False
            last_error = "registry broken"

            def get_string(self, *args, **kwargs):
                raise OSError("denied")

            def list_values(self, *args, **kwargs):
                raise OSError("denied")

            def list_subkeys(self, *args, **kwargs):
                raise OSError("denied")

        backend = self.make_backend(registry=ExplodingRegistry())
        text = backend.diagnostics()
        self.assertIn("Backend: WindowsBackend", text)
        self.assertIn("Registry", text)


# ---------------------------------------------------------------------------
# Real registry, read-only (never writes HKCU)
# ---------------------------------------------------------------------------
@unittest.skipUnless(WINDOWS_OR_LINUX, "Windows-specific read-only checks")
class LiveRegistryReadOnlyTests(unittest.TestCase):
    def test_real_registry_is_readable(self):
        registry = WindowsRegistry()
        self.assertTrue(registry.available)
        subkeys = registry.list_subkeys(HKLM, GPU_CLASS_KEY)
        self.assertIsInstance(subkeys, list)

    def test_real_gpu_class_lists_gpus(self):
        state_dir = temp_state_dir("win-live-")
        self.addCleanup(shutil.rmtree, state_dir, True)
        backend = WindowsBackend(
            registry=WindowsRegistry(),
            process_provider=FakeProcessProvider(),
            state=StateStore(state_dir),
            system=WindowsSystem(),
        )
        try:
            gpus = backend.list_gpus()
        finally:
            backend.close()
        if not gpus:
            self.skipTest("no display adapters readable in this environment")
        known = [gpu for gpu in gpus if gpu.vendor in ("intel", "nvidia", "amd")]
        if not known:
            # GitHub's hosted runners expose only the Microsoft Basic Render
            # Driver, which is not an Intel/NVIDIA/AMD adapter.
            self.skipTest("the machine has no Intel/NVIDIA/AMD display adapter")
        self.assertTrue(all(gpu.id.startswith("windows:gpu:") for gpu in gpus))
        kinds = {gpu.kind for gpu in known}
        self.assertTrue(kinds & {"integrated", "discrete"})

    def test_real_user_gpu_preferences_are_readable(self):
        registry = WindowsRegistry()
        values = registry.list_values(HKCU, WINDOWS_GPU_PREFS_KEY)
        self.assertIsInstance(values, list)
        for name, data, value_type in values:
            self.assertIsInstance(name, str)
            self.assertIsInstance(value_type, int)


if __name__ == "__main__":
    unittest.main()
