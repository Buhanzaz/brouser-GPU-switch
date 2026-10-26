"""Tests for the Tkinter interface and the headless CLI helpers.

GUI tests are skipped automatically when Tkinter or a graphical display is
not available.  Headless tests (self-test, diagnostics, CLI dispatch) never
import Tk.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional

from app.interface import (
    MOCK_OPTION_HIGH_PERFORMANCE,
    MOCK_OPTION_POWER_SAVING,
    ApplyResult,
    GpuOption,
    LaunchResult,
    OsInfo,
    UnsupportedPlatformError,
)
from app.main import (
    MODE_DIAGNOSTICS,
    MODE_SELF_TEST,
    create_backend,
    format_diagnostics,
    mode_of,
    platform_of,
    run,
    run_self_test,
    run_ui_smoke_test,
)
from app.platforms import get_backend
from app.platforms.mock import MockBackend

try:  # Tk is optional for the headless part of this module.
    import tkinter as tk

    _TK_IMPORT_ERROR: Optional[BaseException] = None
except Exception as exc:  # pragma: no cover - depends on the machine
    tk = None  # type: ignore[assignment]
    _TK_IMPORT_ERROR = exc


def _tk_available() -> bool:
    if tk is None:
        return False
    try:
        root = tk.Tk()
    except Exception:
        return False
    try:
        root.destroy()
    except Exception:
        pass
    return True


_TK_AVAILABLE = _tk_available()
_TMP_ROOT = Path(__file__).resolve().parent / ".tmp"


def _make_data_dir(name: str) -> Path:
    """Create a writable temp directory inside the test tree (sandbox-safe)."""
    _TMP_ROOT.mkdir(parents=True, exist_ok=True)
    target = _TMP_ROOT / "{0}-{1}".format(name, os.getpid())
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    return target


def _cli_args(**overrides: Any) -> SimpleNamespace:
    values = {
        "self_test": False,
        "diagnostics": False,
        "ui_smoke_test": False,
        "screenshot_mode": False,
        "mock": False,
        "platform": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _EmptyBackend:
    """Backend that finds nothing at all: the window must survive this."""

    platform_key = "mock"

    def os_info(self) -> OsInfo:
        return OsInfo(platform_key="mock", name="Тестовая система", version="1.0", arch="x86_64", hostname="test-pc")

    def list_gpus(self) -> List[Any]:
        return []

    def list_browsers(self) -> List[Any]:
        return []

    def list_options(self) -> List[GpuOption]:
        return []

    def current_option(self, browser: Any) -> GpuOption:
        return GpuOption(id="mock:default", label="По умолчанию", kind="auto")

    def notes(self) -> List[str]:
        return []

    def is_browser_running(self, browser: Any) -> bool:
        return False

    def running_pids(self, browser: Any) -> List[int]:
        return []

    def apply(self, browser: Any, option: Any) -> ApplyResult:
        return ApplyResult.failure("Нечего настраивать.")

    def pending_changes(self) -> List[Any]:
        return []

    def restore_all(self) -> ApplyResult:
        return ApplyResult.failure("Нечего возвращать.")

    def restore_browser(self, browser: Any) -> ApplyResult:
        return ApplyResult.failure("Нечего возвращать.")

    def launch(self, browser: Any) -> LaunchResult:
        return LaunchResult(ok=False, message="Запуск недоступен.", pid=0)

    def diagnostics(self) -> str:
        return "Backend: EmptyBackend"

    def close(self) -> None:
        return None


class _BrokenBackend:
    """Backend whose every call fails: the self-test must report FAIL."""

    platform_key = "mock"

    def __getattr__(self, name: str) -> Any:
        def _raise(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("backend is broken: {0}".format(name))

        return _raise


class HeadlessCliTests(unittest.TestCase):
    """Self-test, diagnostics and argument dispatch without Tk."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data_dir = _make_data_dir("ui-selftest")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def test_self_test_passes_with_mock_backend(self) -> None:
        buffer = io.StringIO()
        code = run_self_test(get_backend("mock"), out=buffer, data_dir=self.data_dir)
        text = buffer.getvalue()
        self.assertEqual(code, 0, text)
        self.assertIn("PASS  Бэкенд создан: MockBackend", text)
        self.assertIn("Все проверки пройдены", text)
        self.assertNotIn("FAIL", text)
        self.assertEqual(list(self.data_dir.glob(".selftest-*.tmp")), [])

    def test_self_test_is_consistent_for_every_platform_fixture(self) -> None:
        # On a Windows machine the Linux fixture legitimately finds no hardware,
        # so the self-test must report FAIL and exit 1 instead of crashing.
        for platform in ("mock", "windows", "linux"):
            with self.subTest(platform=platform):
                try:
                    backend = create_backend(platform)
                except UnsupportedPlatformError as exc:  # pragma: no cover
                    self.skipTest("платформа недоступна: {0}".format(exc))
                buffer = io.StringIO()
                code = run_self_test(backend, out=buffer, data_dir=self.data_dir)
                try:
                    backend.close()
                except Exception:
                    pass
                text = buffer.getvalue()
                self.assertTrue("Все проверки пройдены" in text or "Итого:" in text, text)
                self.assertIn(code, (0, 1), text)
                self.assertEqual(code, 1 if "FAIL" in text else 0, text)

    def test_self_test_reports_broken_backend(self) -> None:
        buffer = io.StringIO()
        code = run_self_test(_BrokenBackend(), out=buffer, data_dir=self.data_dir)  # type: ignore[arg-type]
        text = buffer.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("FAIL", text)
        self.assertIn("с ошибкой", text)

    def test_diagnostics_report_contains_mock_details(self) -> None:
        report = format_diagnostics(get_backend("mock"))
        self.assertIn("GPU Switch 1.0.0 — диагностика", report)
        self.assertIn("Платформа: демонстрационный режим (mock)", report)
        self.assertIn("Видеокарты (2)", report)
        self.assertIn("Браузеры (4)", report)
        self.assertIn("Google Chrome", report)
        self.assertIn("C:\\Program Files", report)
        self.assertIn("Firefox Developer Edition", report)
        self.assertIn("Запущен: да (PID 4242, 4243)", report)
        self.assertIn("Варианты ускорителя (3)", report)
        self.assertIn("Текущие настройки браузеров", report)
        self.assertIn("Ожидающие изменения (0)", report)
        self.assertIn("Диагностика бэкенда", report)
        self.assertIn("MockBackend", report)
        self.assertIn("Конец отчёта.", report)

    def test_create_backend_unknown_platform_is_friendly(self) -> None:
        with self.assertRaises(UnsupportedPlatformError) as context:
            create_backend("solaris")
        message = str(context.exception)
        self.assertIn("не поддерживается", message)
        self.assertIn("solaris", message)

    def test_mode_and_platform_helpers(self) -> None:
        self.assertEqual(mode_of(_cli_args(self_test=True)), MODE_SELF_TEST)
        self.assertEqual(mode_of(_cli_args(diagnostics=True)), MODE_DIAGNOSTICS)
        self.assertEqual(mode_of(_cli_args()), "gui")
        self.assertIsNone(platform_of(_cli_args()))
        self.assertEqual(platform_of(_cli_args(mock=True)), "mock")
        self.assertEqual(platform_of(_cli_args(platform=" LINUX ")), "linux")

    def test_run_self_test_mode_exits_cleanly(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run(_cli_args(self_test=True, mock=True))
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("Все проверки пройдены", buffer.getvalue())

    def test_run_diagnostics_mode_exits_cleanly(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run(_cli_args(diagnostics=True, mock=True))
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("Браузеры (4)", buffer.getvalue())

    def test_run_unknown_platform_reports_error(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run(_cli_args(diagnostics=True, platform="solaris"))
        self.assertEqual(code, 1)
        self.assertIn("не поддерживается", buffer.getvalue())


@unittest.skipUnless(_TK_AVAILABLE, "Tkinter или графическая среда недоступны")
class InterfaceSmokeTests(unittest.TestCase):
    """Build the real window against the mock backend and inspect it."""

    def setUp(self) -> None:
        from app.ui import GpuSwitchApp

        self.root = tk.Tk()
        self.root.withdraw()
        self.backend = MockBackend()
        self.app = GpuSwitchApp(self.root, self.backend)
        self.app.refresh_now()
        self.root.update_idletasks()

    def tearDown(self) -> None:
        try:
            self.app.shutdown()
        except Exception:
            try:
                self.root.destroy()
            except Exception:
                pass

    def _new_window(self, backend: Any, screenshot_mode: bool = False) -> Any:
        from app.ui import GpuSwitchApp

        root = tk.Tk()
        root.withdraw()
        app = GpuSwitchApp(root, backend, screenshot_mode=screenshot_mode)
        self.addCleanup(self._shutdown_window, app, root)
        return app

    @staticmethod
    def _shutdown_window(app: Any, root: Any) -> None:
        try:
            app.shutdown()
        except Exception:
            try:
                root.destroy()
            except Exception:
                pass

    def test_detection_populates_all_sections(self) -> None:
        self.assertTrue(self.app.detection_finished)
        system_text = str(self.app.system_label.cget("text"))
        self.assertIn("Демо-режим", system_text)
        self.assertIn("Windows 11", system_text)

        gpus = self.app.gpu_rows()
        self.assertEqual(len(gpus), 2)
        self.assertIn("Intel(R) UHD Graphics 630", gpus[0][0])
        self.assertIn("NVIDIA GeForce GTX 1050 Ti", gpus[1][0])

        values = list(self.app.browser_combo["values"])
        self.assertEqual(len(values), 4)
        self.assertIn("Google Chrome", values[0])

        browser = self.app.current_browser()
        self.assertIsNotNone(browser)
        self.assertEqual(browser.id, "mock:chrome")
        self.assertIn("Сейчас включён ускоритель", self.app.current_label.cget("text"))
        self.assertIn("Высокая производительность", self.app.current_label.cget("text"))
        labels = self.app.option_labels()
        self.assertEqual(len(labels), 3)
        self.assertIn("Энергосбережение", " | ".join(labels))
        self.assertIn("Высокая производительность", " | ".join(labels))
        self.assertTrue(self.app.pending_placeholder_visible())
        self.assertEqual(list(self.app.pending_rows()), [])
        self.assertTrue(self.app.status_text)

    def test_browser_selection_updates_state(self) -> None:
        self.app.select_browser_index(1)  # Microsoft Edge: default accelerator
        self.assertIn("Microsoft Edge", self.app.browser_combo.get())
        self.assertIn("По умолчанию", self.app.current_label.cget("text"))
        self.assertTrue(self.app.default_note_visible)
        self.assertTrue(self.app.apply_enabled)

        # Firefox also uses the default accelerator, so the note stays visible.
        self.assertTrue(self.app.select_browser_by_id("mock:firefox"))
        self.assertTrue(self.app.running_warning_visible)
        self.assertTrue(self.app.default_note_visible)
        self.assertFalse(self.app.apply_enabled)

        # The user closed the browser and pressed "Проверить снова".
        self.backend._running.pop("mock:firefox", None)
        self.app.check_again()
        self.assertFalse(self.app.running_warning_visible)
        self.assertTrue(self.app.apply_enabled)

        # Chrome uses a non-default accelerator: the note must disappear.
        self.app.select_browser_index(0)
        self.assertFalse(self.app.default_note_visible)

    def test_apply_is_refused_while_browser_is_running(self) -> None:
        self.assertTrue(self.app.select_browser_by_id("mock:firefox"))
        result = self.app.apply_selected()
        self.assertIsNotNone(result)
        self.assertFalse(result.ok)
        self.assertEqual(list(self.app.pending_rows()), [])
        self.assertTrue(self.app.running_warning_visible)

    def test_apply_creates_pending_change_and_ready_dialog(self) -> None:
        from app.ui import READY_TITLE

        backend = MockBackend(simulate_running=False)
        app = self._new_window(backend)
        app.refresh_now()
        self.assertTrue(app.select_browser_by_id("mock:firefox"))
        self.assertTrue(app.select_option(MOCK_OPTION_POWER_SAVING))

        result = app.apply_selected()
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.root.update_idletasks()

        self.assertTrue(app.ready_dialog_open())
        self.assertEqual(app.ready_dialog_title(), READY_TITLE)
        self.assertEqual(app.ready_dialog_message(), "Все настроено, запустите браузер")

        rows = app.pending_rows()
        self.assertEqual(len(rows), 1)
        joined = " | ".join(str(value) for value in rows[0])
        self.assertIn("Firefox Developer Edition", joined)
        self.assertIn("Энергосбережение", joined)
        self.assertFalse(app.pending_placeholder_visible())

        app.close_ready_dialog()
        self.assertFalse(app.ready_dialog_open())

    def test_restore_all_uses_confirmation_and_reports_browsers(self) -> None:
        backend = MockBackend(simulate_running=False)
        firefox = [browser for browser in backend.list_browsers() if browser.id == "mock:firefox"][0]
        power_option = [option for option in backend.list_options() if option.id == MOCK_OPTION_POWER_SAVING][0]
        backend.apply(firefox, power_option)

        app = self._new_window(backend)
        app.refresh_now()
        self.assertEqual(len(app.pending_rows()), 1)
        # The per-browser restore button belongs to the selected browser.
        self.assertTrue(app.select_browser_by_id("mock:firefox"))
        self.assertTrue(app.restore_browser_button_visible)

        confirmations: List[Any] = []
        notifications: List[Any] = []
        app.confirm = lambda title, message: confirmations.append((title, message)) or True
        app.notify = lambda title, message: notifications.append((title, message))

        result = app.restore_all()
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertTrue(confirmations)
        self.assertTrue(notifications)
        self.assertEqual(list(app.pending_rows()), [])
        self.assertTrue(app.pending_placeholder_visible())
        self.assertIn("Возвращены настройки", str(notifications))

    def test_async_detection_finishes_without_freezing(self) -> None:
        backend = MockBackend()
        app = self._new_window(backend)
        app.start_refresh()
        deadline = time.time() + 10.0
        while not app.detection_finished and time.time() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(app.detection_finished, "обнаружение не завершилось за 10 секунд")
        self.assertEqual(len(app.browser_combo["values"]), 4)

    def test_empty_world_shows_placeholders(self) -> None:
        from app.ui import NO_BROWSERS_SUMMARY, NOT_FOUND

        app = self._new_window(_EmptyBackend())
        app.refresh_now()
        self.assertIsNone(app.current_browser())
        self.assertIn(NOT_FOUND, app.current_label.cget("text"))
        self.assertEqual(list(app.browser_combo["values"]), [])
        self.assertEqual(app.browser_combo.get(), NOT_FOUND)
        self.assertEqual(app.browser_summary_label.cget("text"), NO_BROWSERS_SUMMARY)
        gpus = app.gpu_rows()
        self.assertEqual(len(gpus), 1)
        self.assertEqual(gpus[0][0], NOT_FOUND)
        self.assertEqual(app.option_labels(), [])
        self.assertTrue(app.pending_placeholder_visible())
        self.assertEqual(list(app.pending_rows()), [])

    def test_screenshot_mode_preselects_chrome(self) -> None:
        app = self._new_window(MockBackend(), screenshot_mode=True)
        app.refresh_now()
        browser = app.current_browser()
        self.assertIsNotNone(browser)
        self.assertEqual(browser.id, "mock:chrome")

    def test_ui_smoke_test_helper_succeeds(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run_ui_smoke_test(get_backend("mock"))
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("Смоук-тест интерфейса прошёл успешно", buffer.getvalue())

    def test_run_ui_smoke_mode_uses_mock_by_default(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run(_cli_args(ui_smoke_test=True))
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("демонстрационными данными", buffer.getvalue())
        self.assertIn("Смоук-тест интерфейса прошёл успешно", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
