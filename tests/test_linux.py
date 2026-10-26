"""Unit tests for app.platforms.linux.LinuxBackend.

The tests run on any operating system (including this Windows machine):
there is no /sys, /proc or Linux here, so every input the backend reads is
injected - a fake sysfs tree, a fake /proc tree, a fake home/applications
directory, an injected which() callable and an injected os-release file,
all built inside a temporary directory.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import stat
import sys
import unittest
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

_WORKSPACE = Path(__file__).resolve().parents[1]
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

# Temporary trees live inside the workspace on purpose.  tempfile.mkdtemp()
# creates private (mode 0700) directories, and on some locked-down Windows
# sandboxes such a directory cannot be listed or removed again; plain mkdir()
# with unique names is portable and always cleanable.
_TEMP_BASE = Path(__file__).resolve().parent / ".tmp"


def make_temp_root() -> Path:
    """Create a unique, removable temporary root for one test."""
    _TEMP_BASE.mkdir(parents=True, exist_ok=True)
    for _ in range(20):
        candidate = _TEMP_BASE / ("run-" + uuid.uuid4().hex)
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError("could not create a temporary directory under " + str(_TEMP_BASE))


def tearDownModule() -> None:
    """Remove the shared temporary root, if the platform lets us."""
    shutil.rmtree(_TEMP_BASE, ignore_errors=True)

from app.interface import (
    LINUX,
    LINUX_OPTION_DEFAULT,
    LINUX_OPTION_DRI_PRIME,
    LINUX_OPTION_NVIDIA_OFFLOAD,
    ApplyResult,
    Browser,
    GpuOption,
    LaunchResult,
    OsInfo,
    PendingChange,
)
from app.platforms.linux import (
    LinuxBackend,
    _parse_desktop_entry,
    _parse_exec,
)
from app.state import StateStore


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def pci_dir_name(pci_address: str) -> str:
    """Directory name for a PCI slot.

    Real /sys and /proc use ':' inside PCI addresses, which is not a legal
    file name character on every OS; the tests use '_' and let the backend
    learn the real address from the uevent file content instead.
    """
    return str(pci_address).replace(":", "_")


GOOGLE_CHROME_DESKTOP = """[Desktop Entry]
Version=1.0
Type=Application
Name=Google Chrome
GenericName=Web Browser
Exec=/usr/bin/google-chrome-stable %U
Terminal=false
Icon=google-chrome
Categories=Network;WebBrowser;
MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;
"""

CHROMIUM_DESKTOP = """[Desktop Entry]
Type=Application
Name=Chromium
Exec=/usr/bin/chromium-browser %U
Categories=Network;WebBrowser;
"""

FIREFOX_SYSTEM_DESKTOP = """[Desktop Entry]
Type=Application
Name=Firefox
Exec=/usr/bin/firefox %u
Categories=Network;WebBrowser;
"""

FIREFOX_USER_DESKTOP = """[Desktop Entry]
Type=Application
Name=Firefox (мой)
Exec=/usr/lib/firefox/firefox %u
Categories=Network;WebBrowser;
"""

BRAVE_DESKTOP = """[Desktop Entry]
Type=Application
Name=Brave
Exec=/usr/bin/brave-browser-stable %U
Categories=Network;
"""

EDGE_DESKTOP = """[Desktop Entry]
Type=Application
Name=Microsoft Edge
Exec=/usr/bin/microsoft-edge-stable %U
Categories=Network;WebBrowser;
NoDisplay=true
"""

HIDDEN_DESKTOP = """[Desktop Entry]
Type=Application
Name=Hidden Browser
Exec=/usr/bin/google-chrome-stable %U
Categories=Network;WebBrowser;
Hidden=true
"""

KDE_ONLY_DESKTOP = """[Desktop Entry]
Type=Application
Name=KDE Browser
Exec=/usr/bin/chromium-browser %U
Categories=Network;WebBrowser;
OnlyShowIn=KDE;
"""

BROKEN_TRYEXEC_DESKTOP = """[Desktop Entry]
Type=Application
Name=Broken Browser
Exec=/usr/bin/chromium-browser %U
TryExec=/usr/bin/does-not-exist
Categories=Network;WebBrowser;
"""

MISSING_EXE_DESKTOP = """[Desktop Entry]
Type=Application
Name=Missing Browser
Exec=/usr/bin/no-such-browser %U
Categories=Network;WebBrowser;
"""

LINK_DESKTOP = """[Desktop Entry]
Type=Link
Name=Website
URL=https://example.org
"""

NO_EXEC_DESKTOP = """[Desktop Entry]
Type=Application
Name=No Exec Browser
Categories=Network;WebBrowser;
"""

FLATPAK_FIREFOX_DESKTOP = """[Desktop Entry]
Type=Application
Name=Firefox (Flatpak)
Exec=/usr/bin/flatpak run --branch=stable --arch=x86_64 --command=firefox --file-forwarding org.mozilla.firefox @@u %U @@
Categories=Network;WebBrowser;
"""


class FakeWorld:
    """A complete fake Linux userland built inside one temporary directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.home = self.root / "home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.data_dir = self.root / "data"
        self.sysfs = self.root / "sys"
        self.sysfs.mkdir(parents=True, exist_ok=True)
        self.proc = self.root / "proc"
        self.proc.mkdir(parents=True, exist_ok=True)
        self.os_release = self.root / "etc" / "os-release"
        self.apps: Dict[str, Path] = {
            "system": self.root / "usr" / "share" / "applications",
            "local": self.root / "usr" / "local" / "share" / "applications",
            "user": self.home / ".local" / "share" / "applications",
            "flatpak_system": self.root / "var" / "lib" / "flatpak" / "exports" / "share" / "applications",
            "flatpak_user": self.home / ".local" / "share" / "flatpak" / "exports" / "share" / "applications",
        }
        for path in self.apps.values():
            path.mkdir(parents=True, exist_ok=True)
        self.state = StateStore(self.data_dir)
        self.executables: Dict[str, str] = {}
        self.environ: Dict[str, str] = {
            "XDG_SESSION_TYPE": "x11",
            "XDG_CURRENT_DESKTOP": "GNOME",
        }
        write_text(
            self.os_release,
            'PRETTY_NAME="Ubuntu 24.04 LTS"\nNAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\n',
        )

    # -- executables -------------------------------------------------------
    def register_executable(self, path: str) -> str:
        path = str(path)
        self.executables[path] = path
        base = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        self.executables.setdefault(base, path)
        return path

    def which(self, name: str) -> Optional[str]:
        text = str(name)
        if text in self.executables:
            return self.executables[text]
        base = text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        return self.executables.get(base)

    # -- backend -----------------------------------------------------------
    def backend(self, **overrides: Any) -> LinuxBackend:
        kwargs: Dict[str, Any] = {
            "home": self.home,
            "data_dir": self.data_dir,
            "state": self.state,
            "sysfs_root": self.sysfs,
            "proc_root": self.proc,
            "desktop_dirs": list(self.apps.values()),
            "applications_dir": self.apps["user"],
            "which": self.which,
            "os_release_path": self.os_release,
            "environ": dict(self.environ),
        }
        for key, value in overrides.items():
            if value is None:
                kwargs.pop(key, None)
            else:
                kwargs[key] = value
        return LinuxBackend(**kwargs)

    @property
    def desktop_dirs(self) -> List[Path]:
        return list(self.apps.values())

    # -- sysfs -------------------------------------------------------------
    def _write_gpu_files(
        self,
        device_dir: Path,
        vendor: str,
        device: str,
        driver: str,
        pci: str,
        boot_vga: bool,
        vram_bytes: Optional[int],
        product_name: Optional[str],
        driver_symlink: bool,
        class_code: str,
    ) -> None:
        device_dir.mkdir(parents=True, exist_ok=True)
        write_text(device_dir / "vendor", vendor + "\n")
        write_text(device_dir / "device", device + "\n")
        if class_code:
            write_text(device_dir / "class", class_code + "\n")
        if boot_vga:
            write_text(device_dir / "boot_vga", "1\n")
        if vram_bytes:
            write_text(device_dir / "mem_info_vram_total", str(vram_bytes) + "\n")
        if product_name:
            write_text(device_dir / "product_name", product_name + "\n")
        uevent = ["DRIVER=" + driver]
        if pci:
            uevent.append("PCI_SLOT_NAME=" + pci)
        write_text(device_dir / "uevent", "\n".join(uevent) + "\n")
        if driver:
            if driver_symlink:
                target = "../../../bus/pci/drivers/" + driver
                try:
                    os.symlink(target, device_dir / "driver")
                except (OSError, NotImplementedError):
                    write_text(device_dir / "driver", driver)
            else:
                write_text(device_dir / "driver", driver)

    def add_gpu(
        self,
        card: str = "card0",
        pci: str = "0000:00:02.0",
        vendor: str = "0x8086",
        device: str = "0x9a49",
        driver: str = "i915",
        boot_vga: bool = False,
        vram_bytes: Optional[int] = None,
        product_name: Optional[str] = None,
        driver_symlink: bool = False,
        class_code: str = "0x030000",
    ) -> Path:
        device_dir = self.sysfs / "class" / "drm" / card / "device"
        self._write_gpu_files(
            device_dir,
            vendor,
            device,
            driver,
            pci,
            boot_vga,
            vram_bytes,
            product_name,
            driver_symlink,
            class_code,
        )
        if pci:
            pci_dir = self.sysfs / "bus" / "pci" / "devices" / pci_dir_name(pci)
            self._write_gpu_files(
                pci_dir,
                vendor,
                device,
                driver,
                pci,
                boot_vga,
                vram_bytes,
                product_name,
                False,
                class_code,
            )
        return device_dir

    def add_pci_only_gpu(
        self,
        pci: str = "0000:01:00.0",
        vendor: str = "0x10de",
        device: str = "0x1f95",
        driver: str = "nvidia",
        boot_vga: bool = False,
        class_code: str = "0x030200",
    ) -> Path:
        pci_dir = self.sysfs / "bus" / "pci" / "devices" / pci_dir_name(pci)
        self._write_gpu_files(
            pci_dir,
            vendor,
            device,
            driver,
            pci,
            boot_vga,
            None,
            None,
            False,
            class_code,
        )
        return pci_dir

    def add_connector(self, card: str = "card1", connector: str = "DP-1") -> Path:
        path = self.sysfs / "class" / "drm" / (card + "-" + connector)
        path.mkdir(parents=True, exist_ok=True)
        write_text(path / "status", "connected\n")
        return path

    def add_render_node(self, name: str = "renderD128") -> Path:
        path = self.sysfs / "class" / "drm" / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def add_audio_pci(self, pci: str = "0000:00:1f.3") -> Path:
        path = self.sysfs / "bus" / "pci" / "devices" / pci_dir_name(pci)
        path.mkdir(parents=True, exist_ok=True)
        write_text(path / "class", "0x040300\n")
        write_text(path / "vendor", "0x8086\n")
        write_text(path / "device", "0xa0c8\n")
        return path

    def add_nvidia_info(self, pci: str, model: str) -> Path:
        return write_text(
            self.proc / "driver" / "nvidia" / "gpus" / pci_dir_name(pci) / "information",
            "Model:           " + model + "\nIRQ:             129\nGPU UUID:        GPU-1234\n",
        )

    # -- desktop files -----------------------------------------------------
    def add_desktop(self, where: str, filename: str, text: str) -> Path:
        return write_text(self.apps[where] / filename, text)

    # -- proc --------------------------------------------------------------
    def add_process(
        self,
        pid: int,
        cmdline: List[str],
        comm: Optional[str] = None,
        exe: Optional[str] = None,
    ) -> int:
        pid_dir = self.proc / str(pid)
        pid_dir.mkdir(parents=True, exist_ok=True)
        payload = b"".join(part.encode("utf-8") + b"\x00" for part in cmdline)
        write_bytes(pid_dir / "cmdline", payload)
        if comm is not None:
            write_text(pid_dir / "comm", comm + "\n")
        if exe is not None:
            try:
                os.symlink(exe, pid_dir / "exe")
            except (OSError, NotImplementedError):
                write_text(pid_dir / "exe", exe + "\n")
        return pid


def build_standard_world(root: Path | str) -> FakeWorld:
    world = FakeWorld(root)
    world.add_gpu(
        card="card0",
        pci="0000:00:02.0",
        vendor="0x8086",
        device="0x9a49",
        driver="i915",
        boot_vga=True,
    )
    world.add_gpu(
        card="card1",
        pci="0000:01:00.0",
        vendor="0x10de",
        device="0x1f95",
        driver="nvidia",
        boot_vga=False,
        vram_bytes=8 * 1024 ** 3,
    )
    world.add_nvidia_info("0000:01:00.0", "NVIDIA GeForce GTX 1650")
    world.add_connector("card1", "DP-1")
    world.add_render_node("renderD128")
    world.add_audio_pci()
    for executable in (
        "/usr/bin/google-chrome-stable",
        "/usr/bin/firefox",
        "/usr/lib/firefox/firefox",
        "/usr/bin/chromium-browser",
        "/usr/bin/brave-browser-stable",
        "/usr/bin/flatpak",
        "/usr/bin/microsoft-edge-stable",
    ):
        world.register_executable(executable)
    world.add_desktop("system", "google-chrome.desktop", GOOGLE_CHROME_DESKTOP)
    world.add_desktop("system", "chromium.desktop", CHROMIUM_DESKTOP)
    world.add_desktop("system", "firefox.desktop", FIREFOX_SYSTEM_DESKTOP)
    world.add_desktop("user", "firefox.desktop", FIREFOX_USER_DESKTOP)
    world.add_desktop("system", "brave-browser.desktop", BRAVE_DESKTOP)
    world.add_desktop("system", "microsoft-edge.desktop", EDGE_DESKTOP)
    world.add_desktop("system", "hidden-browser.desktop", HIDDEN_DESKTOP)
    world.add_desktop("system", "kde-only.desktop", KDE_ONLY_DESKTOP)
    world.add_desktop("system", "broken-tryexec.desktop", BROKEN_TRYEXEC_DESKTOP)
    world.add_desktop("system", "missing-exe.desktop", MISSING_EXE_DESKTOP)
    world.add_desktop("system", "not-application.desktop", LINK_DESKTOP)
    world.add_desktop("system", "no-exec.desktop", NO_EXEC_DESKTOP)
    world.add_desktop("flatpak_system", "org.mozilla.firefox.desktop", FLATPAK_FIREFOX_DESKTOP)
    world.add_process(1000, ["/usr/bin/gedit"], comm="gedit")
    return world


class LinuxTestCase(unittest.TestCase):
    """Base class with a temporary directory and the standard fake world."""

    world: FakeWorld

    def setUp(self) -> None:
        self.root = make_temp_root()
        self.addCleanup(shutil.rmtree, str(self.root), True)
        self.world = build_standard_world(self.root / "world")

    def backend(self, **overrides: Any) -> LinuxBackend:
        return self.world.backend(**overrides)

    def browser(self, browser_id: str) -> Browser:
        for browser in self.backend().list_browsers():
            if browser.id == browser_id:
                return browser
        raise AssertionError("browser not found: " + browser_id)

    def option(self, backend: LinuxBackend, option_id: str) -> GpuOption:
        for option in backend.list_options():
            if option.id == option_id:
                return option
        raise AssertionError("option not found: " + option_id)

    def state_entry(self, backend: LinuxBackend, browser_id: str) -> Optional[Dict[str, Any]]:
        return backend.state.get("linux:" + browser_id)


# ---------------------------------------------------------------------------
# OS information
# ---------------------------------------------------------------------------
class TestOsInfo(LinuxTestCase):
    def test_reads_etc_os_release(self) -> None:
        info = self.backend().os_info()
        self.assertIsInstance(info, OsInfo)
        self.assertEqual(info.platform_key, LINUX)
        self.assertEqual(info.name, "Ubuntu 24.04 LTS")
        self.assertEqual(info.version, "24.04")
        self.assertEqual(info.arch, platform.machine())
        self.assertEqual(info.hostname, socket.gethostname())
        self.assertEqual(info.session, "X11")

    def test_wayland_session(self) -> None:
        backend = self.backend(environ={"XDG_SESSION_TYPE": "wayland"})
        self.assertEqual(backend.os_info().session, "Wayland")

    def test_missing_os_release_falls_back(self) -> None:
        backend = self.backend(os_release_path=self.root / "missing-os-release")
        info = backend.os_info()
        self.assertEqual(info.name, "Linux")
        self.assertEqual(info.platform_key, LINUX)

    def test_garbage_os_release_falls_back(self) -> None:
        path = write_text(self.root / "garbage-os-release", "not an os-release\n###\n")
        info = self.backend(os_release_path=path).os_info()
        self.assertEqual(info.name, "Linux")

    def test_os_release_without_pretty_name(self) -> None:
        path = write_text(
            self.root / "minimal-os-release",
            "NAME=Debian\nVERSION_ID=12\n",
        )
        info = self.backend(os_release_path=path).os_info()
        self.assertEqual(info.name, "Debian")
        self.assertEqual(info.version, "12")


# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------
class TestGpuDetection(LinuxTestCase):
    def test_finds_intel_and_nvidia_integrated_first(self) -> None:
        gpus = self.backend().list_gpus()
        self.assertEqual(len(gpus), 2)
        self.assertEqual([gpu.kind for gpu in gpus], ["integrated", "discrete"])
        intel, nvidia = gpus
        self.assertEqual(intel.vendor, "intel")
        self.assertEqual(intel.driver, "i915")
        self.assertEqual(intel.pci_address, "0000:00:02.0")
        self.assertEqual(nvidia.vendor, "nvidia")
        self.assertEqual(nvidia.driver, "nvidia")
        self.assertEqual(nvidia.pci_address, "0000:01:00.0")

    def test_nvidia_name_and_memory_from_files(self) -> None:
        nvidia = [gpu for gpu in self.backend().list_gpus() if gpu.vendor == "nvidia"][0]
        self.assertIn("GTX 1650", nvidia.name)
        self.assertEqual(nvidia.memory_mb, 8192)

    def test_connectors_render_nodes_and_audio_are_ignored(self) -> None:
        gpus = self.backend().list_gpus()
        ids = [gpu.id for gpu in gpus]
        self.assertNotIn("card1-DP-1", " ".join(ids))
        self.assertNotIn("renderD128", " ".join(ids))
        self.assertEqual(len(gpus), 2)

    def test_pci_only_gpu_without_drm_card_is_found(self) -> None:
        world = FakeWorld(self.root / "pci-only")
        world.add_pci_only_gpu(
            pci="0000:01:00.0",
            vendor="0x10de",
            device="0x1f95",
            driver="nvidia",
            class_code="0x030200",
        )
        world.add_nvidia_info("0000:01:00.0", "NVIDIA GeForce GTX 1050 Ti")
        world.add_audio_pci()
        gpus = world.backend().list_gpus()
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0].vendor, "nvidia")
        self.assertEqual(gpus[0].kind, "discrete")
        self.assertIn("GTX 1050 Ti", gpus[0].name)

    def test_virtual_gpu_is_classified_as_virtual(self) -> None:
        world = FakeWorld(self.root / "vm")
        world.add_gpu(
            card="card0",
            pci="0000:00:02.0",
            vendor="0x15ad",
            device="0x0405",
            driver="vmwgfx",
            boot_vga=True,
        )
        gpus = world.backend().list_gpus()
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0].vendor, "virtual")
        self.assertEqual(gpus[0].kind, "virtual")

    def test_amd_apu_with_boot_vga_is_integrated(self) -> None:
        world = FakeWorld(self.root / "amd-apu")
        world.add_gpu(
            card="card0",
            pci="0000:05:00.0",
            vendor="0x1002",
            device="0x164e",
            driver="amdgpu",
            boot_vga=True,
        )
        gpus = world.backend().list_gpus()
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0].vendor, "amd")
        self.assertEqual(gpus[0].kind, "integrated")

    def test_amd_discrete_gpu_is_discrete(self) -> None:
        world = FakeWorld(self.root / "amd-dgpu")
        world.add_gpu(
            card="card1",
            pci="0000:03:00.0",
            vendor="0x1002",
            device="0x73ff",
            driver="amdgpu",
            boot_vga=False,
            product_name="AMD Radeon RX 6600",
        )
        gpus = world.backend().list_gpus()
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0].kind, "discrete")
        self.assertIn("RX 6600", gpus[0].name)

    def test_product_name_file_is_used(self) -> None:
        world = FakeWorld(self.root / "product")
        world.add_gpu(
            card="card0",
            pci="0000:00:02.0",
            vendor="0x8086",
            device="0x9a49",
            driver="i915",
            product_name="Intel Iris Xe Graphics",
        )
        gpus = world.backend().list_gpus()
        self.assertEqual(gpus[0].name, "Intel Iris Xe Graphics")

    def test_empty_sysfs_returns_empty_list(self) -> None:
        backend = self.backend(sysfs_root=self.root / "missing-sysfs")
        self.assertEqual(backend.list_gpus(), [])

    def test_driver_symlink_is_followed(self) -> None:
        world = FakeWorld(self.root / "symlink")
        device_dir = world.add_gpu(
            card="card0",
            pci="0000:00:02.0",
            vendor="0x8086",
            device="0x9a49",
            driver="i915",
            driver_symlink=True,
        )
        if not (device_dir / "driver").is_symlink():
            self.skipTest("symlinks are not supported on this machine")
        gpus = world.backend().list_gpus()
        self.assertEqual(gpus[0].driver, "i915")


# ---------------------------------------------------------------------------
# Browser detection
# ---------------------------------------------------------------------------
class TestBrowserDetection(LinuxTestCase):
    EXPECTED_IDS = {
        "google-chrome",
        "chromium",
        "firefox",
        "brave-browser",
        "org.mozilla.firefox",
    }

    def test_lists_expected_browsers(self) -> None:
        browsers = self.backend().list_browsers()
        self.assertEqual({browser.id for browser in browsers}, self.EXPECTED_IDS)

    def test_sorted_by_display_name(self) -> None:
        browsers = self.backend().list_browsers()
        names = [browser.name for browser in browsers]
        self.assertEqual(names, sorted(names, key=lambda name: name.lower()))

    def test_dedupe_prefers_user_local_desktop_file(self) -> None:
        firefox = self.browser("firefox")
        self.assertEqual(firefox.name, "Firefox (мой)")
        self.assertEqual(
            Path(firefox.desktop_file), self.world.apps["user"] / "firefox.desktop"
        )

    def test_engines_are_mapped(self) -> None:
        engines = {browser.id: browser.engine for browser in self.backend().list_browsers()}
        self.assertEqual(engines["google-chrome"], "chromium")
        self.assertEqual(engines["chromium"], "chromium")
        self.assertEqual(engines["brave-browser"], "chromium")
        self.assertEqual(engines["firefox"], "firefox")
        self.assertEqual(engines["org.mozilla.firefox"], "firefox")

    def test_known_browser_without_webbrowser_category_is_included(self) -> None:
        brave = self.browser("brave-browser")
        self.assertEqual(brave.name, "Brave")
        self.assertEqual(brave.engine, "chromium")

    def test_flatpak_entry_is_parsed(self) -> None:
        browser = self.browser("org.mozilla.firefox")
        self.assertEqual(browser.package, "org.mozilla.firefox")
        self.assertEqual(browser.source, "flatpak")
        self.assertTrue(browser.executable.endswith("flatpak"))
        self.assertEqual(browser.launch_command[0], "/usr/bin/flatpak")
        self.assertEqual(browser.launch_command[1], "run")
        self.assertIn("org.mozilla.firefox", browser.launch_command)
        self.assertIn("org.mozilla.firefox", browser.process_names)
        self.assertIn("firefox", browser.process_names)
        self.assertNotIn("flatpak", browser.process_names)

    def test_process_names_contain_executable_basename(self) -> None:
        chrome = self.browser("google-chrome")
        self.assertIn("chrome", chrome.process_names)
        self.assertIn("google-chrome-stable", chrome.process_names)

    def test_nodisplay_hidden_onlyshowin_and_broken_entries_are_excluded(self) -> None:
        ids = {browser.id for browser in self.backend().list_browsers()}
        for excluded in (
            "microsoft-edge",
            "hidden-browser",
            "kde-only",
            "broken-tryexec",
            "missing-exe",
            "not-application",
            "no-exec",
        ):
            self.assertNotIn(excluded, ids)

    def test_onlyshowin_is_honoured_for_matching_session(self) -> None:
        backend = self.backend(
            environ={"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "KDE"}
        )
        ids = {browser.id for browser in backend.list_browsers()}
        self.assertIn("kde-only", ids)

    def test_missing_desktop_dirs_return_empty(self) -> None:
        backend = self.backend(desktop_dirs=[self.root / "nowhere"])
        self.assertEqual(backend.list_browsers(), [])

    def test_garbage_and_directory_desktop_entries_are_ignored(self) -> None:
        write_bytes(self.world.apps["system"] / "garbage.desktop", b"\x00\x01\x02binary")
        (self.world.apps["system"] / "folder.desktop").mkdir()
        browsers = self.backend().list_browsers()
        self.assertEqual({browser.id for browser in browsers}, self.EXPECTED_IDS)

    def test_environment_prefix_command_is_supported(self) -> None:
        world = FakeWorld(self.root / "env-prefix")
        world.register_executable("/usr/bin/google-chrome-stable")
        world.add_desktop(
            "system",
            "env-chrome.desktop",
            "[Desktop Entry]\nType=Application\nName=Env Chrome\n"
            "Exec=env BAMF_DESKTOP_FILE_HINT=/tmp/x /usr/bin/google-chrome-stable %U\n"
            "Categories=Network;WebBrowser;\n",
        )
        browser = world.backend().list_browsers()[0]
        self.assertEqual(browser.executable, "/usr/bin/google-chrome-stable")
        self.assertEqual(browser.name, "Env Chrome")


# ---------------------------------------------------------------------------
# GPU options
# ---------------------------------------------------------------------------
class TestOptions(LinuxTestCase):
    def test_default_option_is_first(self) -> None:
        options = self.backend().list_options()
        self.assertGreaterEqual(len(options), 1)
        self.assertEqual(options[0].id, LINUX_OPTION_DEFAULT)
        self.assertEqual(options[0].kind, "auto")

    def test_nvidia_offload_when_nvidia_present(self) -> None:
        options = self.backend().list_options()
        by_id = {option.id: option for option in options}
        self.assertIn(LINUX_OPTION_NVIDIA_OFFLOAD, by_id)
        option = by_id[LINUX_OPTION_NVIDIA_OFFLOAD]
        self.assertEqual(option.kind, "discrete")
        self.assertIn("GTX 1650", option.label)
        self.assertEqual(option.payload["__NV_PRIME_RENDER_OFFLOAD"], "1")
        self.assertEqual(option.payload["__GLX_VENDOR_LIBRARY_NAME"], "nvidia")
        self.assertEqual(option.payload["__VK_LAYER_NV_optimus"], "NVIDIA_only")

    def test_no_nvidia_offload_without_nvidia(self) -> None:
        world = FakeWorld(self.root / "amd-only")
        world.add_gpu(
            card="card0",
            pci="0000:05:00.0",
            vendor="0x1002",
            device="0x164e",
            driver="amdgpu",
            boot_vga=True,
        )
        ids = [option.id for option in world.backend().list_options()]
        self.assertNotIn(LINUX_OPTION_NVIDIA_OFFLOAD, ids)

    def test_dri_prime_when_amd_gpu_present(self) -> None:
        world = FakeWorld(self.root / "amd-prime")
        world.add_gpu(
            card="card0",
            pci="0000:00:02.0",
            vendor="0x8086",
            device="0x9a49",
            driver="i915",
            boot_vga=True,
        )
        world.add_gpu(
            card="card1",
            pci="0000:03:00.0",
            vendor="0x1002",
            device="0x73ff",
            driver="amdgpu",
            boot_vga=False,
            product_name="AMD Radeon RX 6600",
        )
        by_id = {option.id: option for option in world.backend().list_options()}
        self.assertIn(LINUX_OPTION_DRI_PRIME, by_id)
        option = by_id[LINUX_OPTION_DRI_PRIME]
        self.assertEqual(option.payload["DRI_PRIME"], "1")
        self.assertIn("RX 6600", option.label)

    def test_no_dri_prime_without_discrete_amd(self) -> None:
        ids = [option.id for option in self.backend().list_options()]
        self.assertNotIn(LINUX_OPTION_DRI_PRIME, ids)

    def test_only_default_option_on_virtual_machine(self) -> None:
        world = FakeWorld(self.root / "virtual-options")
        world.add_gpu(
            card="card0",
            pci="0000:00:02.0",
            vendor="0x1af4",
            device="0x0010",
            driver="virtio_gpu",
            boot_vga=True,
        )
        self.assertEqual(
            [option.id for option in world.backend().list_options()],
            [LINUX_OPTION_DEFAULT],
        )

    def test_option_env_and_describe_launch(self) -> None:
        backend = self.backend()
        nvidia = self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)
        self.assertEqual(
            backend.option_env(nvidia),
            {
                "__NV_PRIME_RENDER_OFFLOAD": "1",
                "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
                "__VK_LAYER_NV_optimus": "NVIDIA_only",
            },
        )
        default = self.option(backend, LINUX_OPTION_DEFAULT)
        self.assertEqual(backend.option_env(default), {})
        hint = backend.describe_launch(nvidia)
        self.assertIn("__NV_PRIME_RENDER_OFFLOAD=1", hint)
        self.assertIn("Браузер", hint)
        self.assertIn("Браузер", backend.describe_launch(default))


# ---------------------------------------------------------------------------
# apply() and current_option()
# ---------------------------------------------------------------------------
class TestApply(LinuxTestCase):
    def test_apply_creates_wrapper_and_override(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        option = self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)
        result = backend.apply(chrome, option)
        self.assertIsInstance(result, ApplyResult)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.warnings, [])

        entry = self.state_entry(backend, "google-chrome")
        self.assertIsNotNone(entry)
        assert entry is not None
        wrapper = Path(entry["wrapper_path"])
        override = Path(entry["override_path"])
        self.assertTrue(wrapper.is_file())
        self.assertTrue(override.is_file())
        self.assertEqual(wrapper.parent, self.world.data_dir / "wrappers")
        self.assertEqual(override, self.world.apps["user"] / "google-chrome.desktop")
        self.assertTrue(str(wrapper).startswith(str(self.world.root)))
        self.assertTrue(str(override).startswith(str(self.world.home)))

        script = wrapper.read_text(encoding="utf-8")
        self.assertIn("#!/bin/sh", script)
        self.assertIn("__NV_PRIME_RENDER_OFFLOAD=1", script)
        self.assertIn("__GLX_VENDOR_LIBRARY_NAME=nvidia", script)
        self.assertIn("__VK_LAYER_NV_optimus=NVIDIA_only", script)
        self.assertIn("/usr/bin/google-chrome-stable", script)
        self.assertIn('"$@"', script)

        if os.name == "posix":
            mode = stat.S_IMODE(wrapper.stat().st_mode)
            self.assertTrue(mode & stat.S_IXUSR, "wrapper must be executable")

    def test_override_carries_markers_and_wrapper_exec(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        option = self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)
        self.assertTrue(backend.apply(chrome, option).ok)
        entry = self.state_entry(backend, "google-chrome")
        assert entry is not None
        override = Path(entry["override_path"])
        parsed = _parse_desktop_entry(override)
        assert parsed is not None
        self.assertEqual(parsed["X-BrowserGpuSwitch-Mode"], LINUX_OPTION_NVIDIA_OFFLOAD)
        self.assertEqual(
            parsed["X-BrowserGpuSwitch-Original-Exec"],
            "/usr/bin/google-chrome-stable %U",
        )
        self.assertEqual(parsed["X-BrowserGpuSwitch-App"], "GPU Switch")
        self.assertEqual(parsed["Name"], "Google Chrome")
        self.assertIn("WebBrowser", parsed["Categories"])
        argv = _parse_exec(parsed["Exec"])
        self.assertEqual(argv[0], str(entry["wrapper_path"]))

    def test_state_entry_fields(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        option = self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)
        self.assertTrue(backend.apply(chrome, option).ok)
        entry = self.state_entry(backend, "google-chrome")
        assert entry is not None
        self.assertEqual(entry["platform"], LINUX)
        self.assertEqual(entry["browser_id"], "google-chrome")
        self.assertEqual(entry["browser_name"], "Google Chrome")
        self.assertEqual(entry["option_id"], LINUX_OPTION_NVIDIA_OFFLOAD)
        self.assertTrue(entry["option_label"])
        self.assertTrue(entry["applied_at"])
        self.assertTrue(entry["description"])
        self.assertTrue(entry["created_by_us"])
        self.assertEqual(entry["original_exec"], "/usr/bin/google-chrome-stable %U")
        self.assertEqual(list(backend.state.keys()), ["linux:google-chrome"])

    def test_original_desktop_is_backed_up(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        option = self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)
        self.assertTrue(backend.apply(chrome, option).ok)
        backup = backend.state.backup_dir("linux:google-chrome") / "original.desktop"
        self.assertTrue(backup.is_file())
        self.assertEqual(
            backup.read_text(encoding="utf-8"),
            (self.world.apps["system"] / "google-chrome.desktop").read_text(encoding="utf-8"),
        )

    def test_system_desktop_file_is_not_modified(self) -> None:
        system_file = self.world.apps["system"] / "google-chrome.desktop"
        before = system_file.read_text(encoding="utf-8")
        backend = self.backend()
        chrome = self.browser("google-chrome")
        self.assertTrue(backend.apply(chrome, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)).ok)
        self.assertEqual(system_file.read_text(encoding="utf-8"), before)

    def test_current_option_after_apply_and_after_restore(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        self.assertEqual(backend.current_option(chrome).id, LINUX_OPTION_DEFAULT)
        self.assertTrue(backend.apply(chrome, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)).ok)
        self.assertEqual(
            backend.current_option(chrome).id, LINUX_OPTION_NVIDIA_OFFLOAD
        )
        self.assertTrue(backend.restore_browser(chrome).ok)
        self.assertEqual(backend.current_option(chrome).id, LINUX_OPTION_DEFAULT)

    def test_current_option_for_other_browser_stays_default(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        chromium = self.browser("chromium")
        self.assertTrue(backend.apply(chrome, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)).ok)
        self.assertEqual(backend.current_option(chromium).id, LINUX_OPTION_DEFAULT)

    def test_list_browsers_still_reports_system_executable_after_apply(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        self.assertTrue(backend.apply(chrome, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)).ok)
        refreshed = self.browser("google-chrome")
        self.assertEqual(refreshed.executable, "/usr/bin/google-chrome-stable")
        self.assertEqual(
            {browser.id for browser in backend.list_browsers()},
            TestBrowserDetection.EXPECTED_IDS,
        )

    def test_apply_refuses_while_browser_is_running(self) -> None:
        self.world.add_process(4242, ["/opt/google/chrome/chrome"], comm="chrome", exe="/opt/google/chrome/chrome")
        backend = self.backend()
        chrome = self.browser("google-chrome")
        self.assertTrue(backend.is_browser_running(chrome))
        result = backend.apply(chrome, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD))
        self.assertFalse(result.ok)
        self.assertIn("запущен", result.message)
        self.assertIn("Закройте", result.message)
        self.assertFalse((self.world.apps["user"] / "google-chrome.desktop").exists())
        self.assertIsNone(self.state_entry(backend, "google-chrome"))
        self.assertEqual(backend.pending_changes(), [])

    def test_apply_refuses_unknown_option(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        result = backend.apply(chrome, GpuOption(id="windows:high-performance", label="Nope"))
        self.assertFalse(result.ok)
        self.assertIn("Неизвестный", result.message)

    def test_apply_refuses_unavailable_option(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        result = backend.apply(chrome, GpuOption(id=LINUX_OPTION_DRI_PRIME, label="AMD"))
        self.assertFalse(result.ok)
        self.assertIn("недоступен", result.message)
        self.assertIsNone(self.state_entry(backend, "google-chrome"))

    def test_apply_refuses_foreign_override(self) -> None:
        backend = self.backend()
        firefox = self.browser("firefox")
        user_file = self.world.apps["user"] / "firefox.desktop"
        before = user_file.read_text(encoding="utf-8")
        result = backend.apply(firefox, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD))
        self.assertFalse(result.ok)
        self.assertIn("не будем", result.message)
        self.assertEqual(user_file.read_text(encoding="utf-8"), before)
        self.assertIsNone(self.state_entry(backend, "firefox"))
        self.assertEqual(list(self.world.data_dir.glob("wrappers/firefox-*.sh")), [])

    def test_default_option_restores(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        self.assertTrue(backend.apply(chrome, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)).ok)
        override = self.world.apps["user"] / "google-chrome.desktop"
        self.assertTrue(override.exists())
        result = backend.apply(chrome, self.option(backend, LINUX_OPTION_DEFAULT))
        self.assertTrue(result.ok, result.message)
        self.assertFalse(override.exists())
        self.assertIsNone(self.state_entry(backend, "google-chrome"))
        self.assertEqual(backend.current_option(chrome).id, LINUX_OPTION_DEFAULT)

    def test_default_option_without_changes_is_success(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        result = backend.apply(chrome, self.option(backend, LINUX_OPTION_DEFAULT))
        self.assertTrue(result.ok)
        self.assertIn("по умолчанию", result.message)

    def test_double_apply_keeps_first_original_data(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        option = self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)
        self.assertTrue(backend.apply(chrome, option).ok)
        first = self.state_entry(backend, "google-chrome")
        assert first is not None
        first_exec = first["original_exec"]
        first_wrapper = first["wrapper_path"]
        self.assertTrue(backend.apply(chrome, option).ok)
        second = self.state_entry(backend, "google-chrome")
        assert second is not None
        self.assertEqual(second["original_exec"], first_exec)
        self.assertEqual(second["original_desktop_path"], first["original_desktop_path"])
        self.assertTrue(second["created_by_us"])
        self.assertEqual(second["wrapper_path"], first_wrapper)
        self.assertEqual(len(list(self.world.data_dir.glob("wrappers/*.sh"))), 1)

    def test_switching_mode_replaces_wrapper_but_keeps_original(self) -> None:
        world = build_standard_world(self.root / "multi")
        world.add_gpu(
            card="card2",
            pci="0000:03:00.0",
            vendor="0x1002",
            device="0x73ff",
            driver="amdgpu",
            boot_vga=False,
            product_name="AMD Radeon RX 6600",
        )
        backend = world.backend()
        chrome = [browser for browser in backend.list_browsers() if browser.id == "google-chrome"][0]
        nvidia = [option for option in backend.list_options() if option.id == LINUX_OPTION_NVIDIA_OFFLOAD][0]
        prime = [option for option in backend.list_options() if option.id == LINUX_OPTION_DRI_PRIME][0]
        self.assertTrue(backend.apply(chrome, nvidia).ok)
        first = backend.state.get("linux:google-chrome")
        assert first is not None
        self.assertTrue(backend.apply(chrome, prime).ok)
        second = backend.state.get("linux:google-chrome")
        assert second is not None
        self.assertEqual(second["original_exec"], first["original_exec"])
        self.assertTrue(second["created_by_us"])
        self.assertNotEqual(second["wrapper_path"], first["wrapper_path"])
        self.assertFalse(Path(first["wrapper_path"]).exists())
        self.assertTrue(Path(second["wrapper_path"]).exists())
        self.assertEqual(backend.current_option(chrome).id, LINUX_OPTION_DRI_PRIME)

    def test_apply_without_desktop_file_uses_browser_command(self) -> None:
        backend = self.backend(desktop_dirs=[self.root / "empty-apps"])
        browser = Browser(
            id="google-chrome",
            name="Google Chrome",
            executable="/usr/bin/google-chrome-stable",
            launch_command=("/usr/bin/google-chrome-stable", "--new-window"),
            engine="chromium",
        )
        result = backend.apply(browser, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD))
        self.assertTrue(result.ok, result.message)
        self.assertTrue(any("Системный ярлык" in warning for warning in result.warnings))
        entry = self.state_entry(backend, "google-chrome")
        assert entry is not None
        script = Path(entry["wrapper_path"]).read_text(encoding="utf-8")
        self.assertIn("/usr/bin/google-chrome-stable", script)

    def test_apply_keeps_paths_inside_the_temporary_world(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        self.assertTrue(backend.apply(chrome, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)).ok)
        entry = self.state_entry(backend, "google-chrome")
        assert entry is not None
        for key in ("override_path", "wrapper_path"):
            self.assertTrue(
                Path(entry[key]).is_absolute()
                and str(Path(entry[key]).resolve()).startswith(str(self.world.root.resolve())),
                key + " must stay inside the fixture root",
            )

    def test_invalid_arguments_return_failure(self) -> None:
        backend = self.backend()
        self.assertFalse(backend.apply(None, None).ok)
        chrome = self.browser("google-chrome")
        self.assertFalse(backend.apply(chrome, None).ok)


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------
class TestRestore(LinuxTestCase):
    def _apply_nvidia(self, backend: LinuxBackend, browser_id: str = "google-chrome") -> Dict[str, Any]:
        browser = self.browser(browser_id)
        option = self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)
        result = backend.apply(browser, option)
        self.assertTrue(result.ok, result.message)
        entry = self.state_entry(backend, browser_id)
        assert entry is not None
        return entry

    def test_restore_all_deletes_only_our_files(self) -> None:
        backend = self.backend()
        entry = self._apply_nvidia(backend)
        backup_dir = backend.state.backup_dir("linux:google-chrome")
        self.assertTrue(backup_dir.is_dir())
        result = backend.restore_all()
        self.assertTrue(result.ok, result.message)
        self.assertIn("возвращены", result.message)
        self.assertFalse(Path(entry["override_path"]).exists())
        self.assertFalse(Path(entry["wrapper_path"]).exists())
        self.assertFalse(backend.state.backup_file("linux:google-chrome", "original.desktop").exists())
        self.assertIsNone(self.state_entry(backend, "google-chrome"))
        self.assertEqual(backend.pending_changes(), [])
        self.assertEqual(backend.current_option(self.browser("google-chrome")).id, LINUX_OPTION_DEFAULT)

    def test_restore_all_keeps_foreign_desktop_files(self) -> None:
        backend = self.backend()
        foreign = self.world.apps["user"] / "firefox.desktop"
        before = foreign.read_text(encoding="utf-8")
        self._apply_nvidia(backend)
        self.assertTrue(backend.restore_all().ok)
        self.assertEqual(foreign.read_text(encoding="utf-8"), before)

    def test_restore_all_is_idempotent(self) -> None:
        backend = self.backend()
        self._apply_nvidia(backend)
        self.assertTrue(backend.restore_all().ok)
        second = backend.restore_all()
        self.assertTrue(second.ok)
        self.assertIn("нечего", second.message)

    def test_restore_browser_touches_only_that_browser(self) -> None:
        backend = self.backend()
        chrome_entry = self._apply_nvidia(backend, "google-chrome")
        chromium_entry = self._apply_nvidia(backend, "chromium")
        result = backend.restore_browser(self.browser("google-chrome"))
        self.assertTrue(result.ok, result.message)
        self.assertFalse(Path(chrome_entry["override_path"]).exists())
        self.assertFalse(Path(chrome_entry["wrapper_path"]).exists())
        self.assertTrue(Path(chromium_entry["override_path"]).exists())
        self.assertTrue(Path(chromium_entry["wrapper_path"]).exists())
        self.assertEqual([change.browser_id for change in backend.pending_changes()], ["chromium"])

    def test_restore_browser_without_changes_is_success(self) -> None:
        backend = self.backend()
        result = backend.restore_browser(self.browser("google-chrome"))
        self.assertTrue(result.ok)
        self.assertIn("изменений нет", result.message)

    def test_restore_ignores_other_platform_entries(self) -> None:
        backend = self.backend()
        windows_file = write_text(self.root / "foreign-windows-file.txt", "keep me")
        backend.state.put(
            "windows:notepad",
            {
                "platform": "windows",
                "created_by_us": True,
                "override_path": str(windows_file),
            },
        )
        result = backend.restore_all()
        self.assertTrue(result.ok)
        self.assertIn("нечего", result.message)
        self.assertTrue(windows_file.exists())
        self.assertIsNotNone(backend.state.get("windows:notepad"))

    def test_restore_keeps_override_modified_by_another_program(self) -> None:
        backend = self.backend()
        entry = self._apply_nvidia(backend)
        override = Path(entry["override_path"])
        write_text(override, "[Desktop Entry]\nType=Application\nName=Hijacked\nExec=/bin/true\n")
        result = backend.restore_all()
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.warnings)
        self.assertTrue(override.exists())
        self.assertFalse(Path(entry["wrapper_path"]).exists())
        self.assertIsNone(self.state_entry(backend, "google-chrome"))

    def test_restore_tolerates_missing_files(self) -> None:
        backend = self.backend()
        entry = self._apply_nvidia(backend)
        Path(entry["override_path"]).unlink()
        Path(entry["wrapper_path"]).unlink()
        result = backend.restore_all()
        self.assertTrue(result.ok, result.message)
        self.assertIsNone(self.state_entry(backend, "google-chrome"))

    def test_restore_never_deletes_entry_not_created_by_us(self) -> None:
        backend = self.backend()
        foreign = write_text(self.root / "foreign-desktop.desktop", "[Desktop Entry]\nName=Other\n")
        backend.state.put(
            "linux:custom",
            {
                "platform": LINUX,
                "browser_id": "custom",
                "browser_name": "Custom",
                "option_id": LINUX_OPTION_NVIDIA_OFFLOAD,
                "option_label": "NVIDIA",
                "applied_at": "2026-01-01T00:00:00+03:00",
                "description": "custom",
                "created_by_us": False,
                "override_path": str(foreign),
            },
        )
        result = backend.restore_all()
        self.assertTrue(result.ok, result.message)
        self.assertTrue(foreign.exists())
        self.assertTrue(any("создан не приложением" in warning for warning in result.warnings))
        self.assertIsNone(backend.state.get("linux:custom"))

    def test_restore_removes_backup_directory(self) -> None:
        backend = self.backend()
        self._apply_nvidia(backend)
        backup_dir = backend.state.backup_dir("linux:google-chrome")
        self.assertTrue(backup_dir.is_dir())
        self.assertTrue(backend.restore_all().ok)
        self.assertFalse(backup_dir.exists())

    def test_restore_all_handles_several_browsers(self) -> None:
        backend = self.backend()
        self._apply_nvidia(backend, "google-chrome")
        self._apply_nvidia(backend, "chromium")
        self.assertEqual(len(backend.pending_changes()), 2)
        result = backend.restore_all()
        self.assertTrue(result.ok, result.message)
        self.assertIn("2", result.message)
        self.assertEqual(backend.pending_changes(), [])


# ---------------------------------------------------------------------------
# Process detection
# ---------------------------------------------------------------------------
class TestRunningDetection(LinuxTestCase):
    def test_detects_process_by_executable_symlink(self) -> None:
        self.world.add_process(
            2001,
            ["/usr/bin/wrapper-helper"],
            comm="wrapper-helper",
            exe="/opt/google/chrome/chrome",
        )
        backend = self.backend()
        chrome = self.browser("google-chrome")
        self.assertEqual(backend.running_pids(chrome), [2001])
        self.assertTrue(backend.is_browser_running(chrome))

    def test_detects_process_by_cmdline_basename(self) -> None:
        self.world.add_process(
            2002,
            ["/usr/bin/google-chrome-stable", "--type=renderer"],
            comm="chrome",
        )
        self.assertIn(2002, self.backend().running_pids(self.browser("google-chrome")))

    def test_detects_process_by_deleted_executable(self) -> None:
        self.world.add_process(
            2003,
            ["/usr/bin/helper"],
            comm="helper",
            exe="/opt/google/chrome/chrome (deleted)",
        )
        self.assertIn(2003, self.backend().running_pids(self.browser("google-chrome")))

    def test_detects_flatpak_application_id(self) -> None:
        self.world.add_process(
            2004,
            ["/usr/bin/flatpak", "run", "--branch=stable", "org.mozilla.firefox"],
            comm="flatpak",
        )
        flatpak = self.browser("org.mozilla.firefox")
        self.assertEqual(self.backend().running_pids(flatpak), [2004])

    def test_ignores_unrelated_processes_and_entries(self) -> None:
        self.world.add_process(2005, ["/usr/bin/gedit"], comm="gedit")
        write_text(self.world.proc / "self", "1")
        write_text(self.world.proc / "not-a-pid", "x")
        backend = self.backend()
        self.assertEqual(backend.running_pids(self.browser("google-chrome")), [])
        self.assertFalse(backend.is_browser_running(self.browser("firefox")))

    def test_missing_proc_root_returns_empty(self) -> None:
        backend = self.backend(proc_root=self.root / "missing-proc")
        self.assertEqual(backend.running_pids(self.browser("google-chrome")), [])
        self.assertFalse(backend.is_browser_running(self.browser("google-chrome")))

    def test_permission_error_is_swallowed(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        with mock.patch("app.platforms.linux.os.listdir", side_effect=PermissionError(13, "denied")):
            self.assertEqual(backend.running_pids(chrome), [])
            self.assertFalse(backend.is_browser_running(chrome))


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
class TestLaunch(LinuxTestCase):
    def test_launch_uses_detached_popen_with_home_cwd(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        fake_process = mock.MagicMock()
        fake_process.pid = 4242
        with mock.patch("app.platforms.linux.subprocess.Popen", return_value=fake_process) as popen:
            result = backend.launch(chrome)
        self.assertIsInstance(result, LaunchResult)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.pid, 4242)
        popen.assert_called_once()
        args, kwargs = popen.call_args
        self.assertEqual(list(args[0])[0], "/usr/bin/google-chrome-stable")
        self.assertTrue(kwargs["start_new_session"])
        self.assertTrue(kwargs["close_fds"])
        self.assertEqual(kwargs["cwd"], str(self.world.home))
        self.assertIsInstance(kwargs["env"], dict)
        self.assertNotIn("__NV_PRIME_RENDER_OFFLOAD", kwargs["env"])

    def test_launch_uses_applied_option_environment(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        self.assertTrue(backend.apply(chrome, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)).ok)
        fake_process = mock.MagicMock()
        fake_process.pid = 4343
        with mock.patch("app.platforms.linux.subprocess.Popen", return_value=fake_process) as popen:
            result = backend.launch(chrome)
        self.assertTrue(result.ok)
        _, kwargs = popen.call_args
        self.assertEqual(kwargs["env"]["__NV_PRIME_RENDER_OFFLOAD"], "1")
        self.assertEqual(kwargs["env"]["__GLX_VENDOR_LIBRARY_NAME"], "nvidia")

    def test_launch_failure_is_reported_in_russian(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        with mock.patch(
            "app.platforms.linux.subprocess.Popen", side_effect=OSError(2, "missing")
        ):
            result = backend.launch(chrome)
        self.assertFalse(result.ok)
        self.assertIn("Не удалось", result.message)

    def test_launch_without_command_fails(self) -> None:
        backend = self.backend()
        empty = Browser(id="empty", name="Пустой", executable="", launch_command=())
        with mock.patch("app.platforms.linux.subprocess.Popen") as popen:
            result = backend.launch(empty)
        self.assertFalse(result.ok)
        popen.assert_not_called()


# ---------------------------------------------------------------------------
# Notes, diagnostics, contract
# ---------------------------------------------------------------------------
class TestNotesDiagnosticsContract(LinuxTestCase):
    def test_platform_key(self) -> None:
        self.assertEqual(self.backend().platform_key, LINUX)

    def test_injected_paths_are_used(self) -> None:
        backend = self.backend()
        self.assertEqual(backend.sysfs_root, self.world.sysfs)
        self.assertEqual(backend.proc_root, self.world.proc)
        self.assertEqual(backend.home, self.world.home)
        self.assertEqual(backend.applications_dir, self.world.apps["user"])
        self.assertEqual(backend.data_dir, self.world.data_dir)

    def test_notes_are_friendly_russian_strings(self) -> None:
        notes = self.backend().notes()
        self.assertTrue(notes)
        self.assertTrue(all(isinstance(note, str) and note for note in notes))
        self.assertTrue(any("пользовател" in note for note in notes))

    def test_notes_mention_wayland_and_flatpak(self) -> None:
        backend = self.backend(environ={"XDG_SESSION_TYPE": "wayland"})
        notes = " ".join(backend.notes())
        self.assertIn("Wayland", notes)
        self.assertIn("Flatpak", notes)

    def test_diagnostics_contains_technical_sections(self) -> None:
        backend = self.backend()
        report = backend.diagnostics()
        self.assertIsInstance(report, str)
        for fragment in (
            "Backend: LinuxBackend",
            "GPUs: 2",
            "Browsers: 5",
            "Google Chrome",
            "linux:nvidia-offload",
            "sysfs root:",
            "Errors:",
        ):
            self.assertIn(fragment, report)

    def test_repeated_calls_do_not_accumulate_errors(self) -> None:
        backend = self.backend()
        for _ in range(3):
            backend.list_gpus()
            backend.list_browsers()
            backend.list_options()
            backend.diagnostics()
        self.assertNotIn("Errors:\n", backend.diagnostics())

    def test_pending_changes_maps_state_entries(self) -> None:
        backend = self.backend()
        chrome = self.browser("google-chrome")
        self.assertTrue(backend.apply(chrome, self.option(backend, LINUX_OPTION_NVIDIA_OFFLOAD)).ok)
        changes = backend.pending_changes()
        self.assertEqual(len(changes), 1)
        change = changes[0]
        self.assertIsInstance(change, PendingChange)
        self.assertEqual(change.key, "linux:google-chrome")
        self.assertEqual(change.platform, LINUX)
        self.assertEqual(change.browser_name, "Google Chrome")
        self.assertEqual(change.option_id, LINUX_OPTION_NVIDIA_OFFLOAD)
        self.assertTrue(change.description)
        self.assertTrue(change.applied_at)

    def test_public_api_never_raises_on_missing_everything(self) -> None:
        world = FakeWorld(self.root / "hostile")
        backend = world.backend(
            sysfs_root=self.root / "no-sysfs",
            proc_root=self.root / "no-proc",
            desktop_dirs=[self.root / "no-apps"],
            applications_dir=self.root / "no-apps",
            os_release_path=self.root / "no-os-release",
        )
        browser = Browser(id="ghost", name="Ghost", executable="/nonexistent/ghost")
        self.assertIsInstance(backend.os_info(), OsInfo)
        self.assertEqual(backend.list_gpus(), [])
        self.assertEqual(backend.list_browsers(), [])
        options = backend.list_options()
        self.assertEqual(options[0].id, LINUX_OPTION_DEFAULT)
        self.assertEqual(backend.current_option(browser).id, LINUX_OPTION_DEFAULT)
        self.assertFalse(backend.is_browser_running(browser))
        self.assertEqual(backend.running_pids(browser), [])
        self.assertEqual(backend.pending_changes(), [])
        self.assertTrue(isinstance(backend.apply(browser, options[0]), ApplyResult))
        self.assertTrue(isinstance(backend.restore_all(), ApplyResult))
        self.assertTrue(isinstance(backend.restore_browser(browser), ApplyResult))
        self.assertTrue(isinstance(backend.launch(browser), LaunchResult))
        self.assertTrue(backend.notes())
        self.assertTrue(backend.diagnostics())
        backend.close()

    def test_default_desktop_dirs_include_the_user_local_directory(self) -> None:
        world = FakeWorld(self.root / "defaults")
        world.register_executable("/usr/bin/google-chrome-stable")
        world.add_desktop("user", "google-chrome.desktop", GOOGLE_CHROME_DESKTOP)
        backend = world.backend(desktop_dirs=None, applications_dir=None)
        self.assertEqual(backend.applications_dir, world.apps["user"])
        browsers = backend.list_browsers()
        self.assertEqual([browser.id for browser in browsers], ["google-chrome"])

    def test_xdg_data_home_redirects_applications_dir(self) -> None:
        world = FakeWorld(self.root / "xdg")
        xdg_apps = world.root / "xdg-data" / "applications"
        xdg_apps.mkdir(parents=True)
        backend = world.backend(
            applications_dir=None,
            desktop_dirs=None,
            environ={"XDG_DATA_HOME": str(world.root / "xdg-data")},
        )
        self.assertEqual(backend.applications_dir, xdg_apps)

    def test_close_is_a_noop(self) -> None:
        backend = self.backend()
        self.assertIsNone(backend.close())
        self.assertEqual(backend.list_gpus(), backend.list_gpus())


if __name__ == "__main__":
    unittest.main()
