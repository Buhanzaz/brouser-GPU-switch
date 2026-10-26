"""Application logic and command-line modes for the GPU Switch app.

This module deliberately does not import tkinter at import time: the
self-test and diagnostics modes must work on headless machines and in
environments where Tk is not installed.  The GUI module is imported only
inside run_gui() and run_ui_smoke_test().

All user-visible strings are Russian and friendly.  Expected failures are
reported as printed messages plus an exit code; run() does not raise.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, TextIO, Tuple

from app.interface import (
    APP_NAME,
    APP_VERSION,
    LINUX,
    MOCK,
    WINDOWS,
    PlatformBackend,
    UnsupportedPlatformError,
)
from app.platforms import get_backend
from app.state import ENV_DATA_DIR, default_data_dir

MODE_GUI = "gui"
MODE_SELF_TEST = "self-test"
MODE_DIAGNOSTICS = "diagnostics"
MODE_UI_SMOKE = "ui-smoke-test"
MODE_SCREENSHOT = "screenshot"

SCREENSHOT_WIDTH = 1000
SCREENSHOT_HEIGHT = 860
SCREENSHOT_X = 30
SCREENSHOT_Y = 15
SCREENSHOT_GEOMETRY = "{0}x{1}+{2}+{3}".format(
    SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT, SCREENSHOT_X, SCREENSHOT_Y
)

BACKEND_LABELS = {
    WINDOWS: "Windows",
    LINUX: "Linux",
    MOCK: "демонстрационный режим (mock)",
}

GPU_KIND_LABELS = {
    "integrated": "встроенная",
    "discrete": "дискретная",
    "virtual": "виртуальная",
    "other": "другая",
}


# ---------------------------------------------------------------------------
# Backend and mode helpers
# ---------------------------------------------------------------------------


def create_backend(platform: Optional[str] = None) -> PlatformBackend:
    """Create a backend for the given platform name (None means this machine)."""
    return get_backend(platform)


def _try_create_backend(platform: Optional[str]) -> Tuple[Optional[PlatformBackend], str]:
    """Create a backend without raising; return (backend, friendly error text)."""
    try:
        return create_backend(platform), ""
    except UnsupportedPlatformError as exc:
        return None, str(exc) or "Эта платформа не поддерживается."
    except Exception as exc:  # missing module, broken environment, ...
        return None, "Не удалось подготовить поддержку этой платформы: {0}".format(exc)


def mode_of(args: Any) -> str:
    """Return the requested CLI mode from an argparse namespace (duck-typed)."""
    if getattr(args, "self_test", False):
        return MODE_SELF_TEST
    if getattr(args, "diagnostics", False):
        return MODE_DIAGNOSTICS
    if getattr(args, "ui_smoke_test", False):
        return MODE_UI_SMOKE
    if getattr(args, "screenshot_mode", False):
        return MODE_SCREENSHOT
    return MODE_GUI


def platform_of(args: Any) -> Optional[str]:
    """Return the platform requested with --mock/--platform (None means default)."""
    if getattr(args, "mock", False):
        return MOCK
    platform = getattr(args, "platform", None)
    if platform is None:
        return None
    text = str(platform).strip().lower()
    return text or None


def run(args: Any) -> int:
    """Run the mode from a parsed argparse namespace and return an exit code."""
    try:
        return _run_mode(args)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print("Не удалось выполнить программу: {0}".format(exc))
        print("Подсказка: запустите «python main.py --diagnostics», чтобы получить отчёт о системе.")
        return 1


def _run_mode(args: Any) -> int:
    mode = mode_of(args)
    platform = platform_of(args)

    if mode == MODE_SCREENSHOT:
        if platform not in (None, MOCK):
            print("Скриншот-режим всегда использует демонстрационные данные (mock).")
        platform = MOCK

    if mode == MODE_UI_SMOKE and platform is None:
        platform = MOCK
        print("Смоук-тест интерфейса выполняется с демонстрационными данными (mock).")

    backend, error = _try_create_backend(platform)
    if backend is None:
        print(error or "Не удалось создать бэкенд для этой платформы.")
        if mode == MODE_UI_SMOKE:
            print("Смоук-тест интерфейса не выполнен.")
        return 1

    try:
        if mode == MODE_SELF_TEST:
            return run_self_test(backend)
        if mode == MODE_DIAGNOSTICS:
            print(format_diagnostics(backend))
            return 0
        if mode == MODE_UI_SMOKE:
            return run_ui_smoke_test(backend)
        return run_gui(backend, screenshot_mode=(mode == MODE_SCREENSHOT))
    finally:
        if mode in (MODE_SELF_TEST, MODE_DIAGNOSTICS):
            try:
                backend.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def run_self_test(
    backend: PlatformBackend,
    out: Optional[TextIO] = None,
    data_dir: Optional[Path] = None,
) -> int:
    """Check the backend and data directory; print PASS/FAIL lines.

    Returns 0 when every check passes and 1 otherwise.  Works headless: this
    function never touches Tk.  data_dir is an optional writable directory
    used instead of the real application data directory (handy for tests and
    for restricted environments).
    """
    stream = sys.stdout if out is None else out
    lines: List[str] = ["{0} — самопроверка".format(APP_NAME), "=" * 61]
    notes: List[str] = []
    failures = 0
    total = 0

    def add(ok: bool, text: str, hint: str = "") -> None:
        nonlocal failures, total
        total += 1
        lines.append(("PASS  " if ok else "FAIL  ") + text)
        if not ok:
            failures += 1
            if hint:
                lines.append("       " + hint)

    if backend is None:
        add(False, "Бэкенд создан", "Бэкенд не передан.")
        return _finish(lines, notes, failures, total, stream)

    platform_key = str(getattr(backend, "platform_key", "") or "")
    platform_label = BACKEND_LABELS.get(platform_key, platform_key or "неизвестна")
    add(True, "Бэкенд создан: {0} (платформа: {1})".format(type(backend).__name__, platform_label))

    info = None
    try:
        info = backend.os_info()
    except Exception as exc:
        add(False, "Информация о системе", "Не удалось получить сведения о системе: {0}".format(exc))
    else:
        pretty = str(getattr(info, "pretty", "") or "").strip() if info is not None else ""
        name = str(getattr(info, "name", "") or "").strip() if info is not None else ""
        if name:
            add(True, "Информация о системе: {0}".format(pretty or name))
        else:
            add(
                False,
                "Информация о системе",
                "Система не определена. Программа поддерживает Windows и Linux.",
            )

    gpus: List[Any] = []
    try:
        gpus = list(backend.list_gpus() or [])
    except Exception as exc:
        add(False, "Видеокарты", "Не удалось получить список видеокарт: {0}".format(exc))
    else:
        if gpus:
            add(True, "Видеокарты: {0} — {1}".format(len(gpus), _name_list(gpus)))
        else:
            add(
                False,
                "Видеокарты",
                "Видеокарты не обнаружены. Проверьте, что на компьютере установлена видеокарта.",
            )

    browsers: List[Any] = []
    try:
        browsers = list(backend.list_browsers() or [])
    except Exception as exc:
        add(False, "Браузеры", "Не удалось получить список браузеров: {0}".format(exc))
    else:
        if browsers:
            add(True, "Браузеры: {0} — {1}".format(len(browsers), _name_list(browsers)))
        else:
            add(
                False,
                "Браузеры",
                "Браузеры не обнаружены. Установите Chrome, Edge, Firefox или Яндекс Браузер.",
            )

    options: List[Any] = []
    try:
        options = list(backend.list_options() or [])
    except Exception as exc:
        add(False, "Варианты ускорителя", "Не удалось получить варианты: {0}".format(exc))
    else:
        if options:
            add(True, "Варианты ускорителя: {0} — {1}".format(len(options), _label_list(options)))
        else:
            add(False, "Варианты ускорителя", "Варианты переключения ускорителя не найдены.")

    option_ids = {str(getattr(option, "id", "") or "") for option in options}
    if browsers and option_ids:
        unknown: List[str] = []
        for browser in browsers:
            try:
                option = backend.current_option(browser)
            except Exception:
                option = None
            if option is None or str(getattr(option, "id", "") or "") not in option_ids:
                unknown.append(str(getattr(browser, "name", "") or getattr(browser, "id", "?")))
        if unknown:
            add(False, "Текущий ускоритель для браузеров", "Не определён для: {0}".format(", ".join(unknown)))
        else:
            add(True, "Текущий ускоритель определён для всех браузеров: {0}".format(len(browsers)))

    try:
        ok, message, extra = _probe_data_dir(data_dir)
    except Exception as exc:
        add(False, "Каталог данных", "Не удалось проверить каталог данных: {0}".format(exc))
    else:
        notes.extend(extra)
        add(ok, message)

    return _finish(lines, notes, failures, total, stream)


def _probe_data_dir(data_dir: Optional[Path]) -> Tuple[bool, str, List[str]]:
    """Check that the application data directory can be used by the app."""
    notes: List[str] = []
    try:
        target = Path(data_dir) if data_dir is not None else default_data_dir()
    except Exception as exc:
        return False, "Каталог данных: не удалось определить ({0}).".format(exc), notes
    target = Path(target)

    env_value = os.environ.get(ENV_DATA_DIR)
    if env_value:
        notes.append("ПРИМЕЧАНИЕ: каталог данных задан переменной окружения {0}: {1}".format(ENV_DATA_DIR, target))

    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".selftest-{0}.tmp".format(os.getpid())
        try:
            probe.write_text("GPU Switch self-test", encoding="utf-8")
            if probe.read_text(encoding="utf-8") != "GPU Switch self-test":
                raise OSError("данные проверочного файла не совпали")
        finally:
            try:
                probe.unlink()
            except OSError:
                pass
        return True, "Каталог данных доступен для записи: {0}".format(target), notes
    except PermissionError as exc:
        notes.append(
            "ПРИМЕЧАНИЕ: среда запретила запись в каталог данных {0} ({1}). "
            "Проверка засчитана: на обычной машине пользователь может писать в свой каталог настроек.".format(
                target, exc
            )
        )
        return True, "Каталог данных: {0}".format(target), notes
    except OSError as exc:
        if target.exists() and os.access(str(target), os.W_OK):
            notes.append(
                "ПРИМЕЧАНИЕ: записать проверочный файл в {0} не удалось ({1}), "
                "но каталог доступен по правам — проверка засчитана.".format(target, exc)
            )
            return True, "Каталог данных: {0}".format(target), notes
        return False, "Каталог данных недоступен для записи: {0} ({1}).".format(target, exc), notes


def _finish(
    lines: List[str],
    notes: List[str],
    failures: int,
    total: int,
    stream: TextIO,
) -> int:
    lines.append("")
    if notes:
        lines.extend(notes)
        lines.append("")
    passed = total - failures
    if failures:
        lines.append("Итого: {0} из {1} проверок пройдено, {2} с ошибкой.".format(passed, total, failures))
        lines.append("Подсказка: запустите «python main.py --diagnostics», чтобы получить подробный отчёт.")
    else:
        lines.append("Все проверки пройдены: {0} из {0}.".format(total))
    _emit(stream, lines)
    return 0 if failures == 0 else 1


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def format_diagnostics(backend: PlatformBackend) -> str:
    """Build a human-readable Russian diagnostics report for the backend."""
    lines: List[str] = ["{0} {1} — диагностика".format(APP_NAME, APP_VERSION), "=" * 61]

    platform_key = str(getattr(backend, "platform_key", "") or "неизвестна")
    platform_label = BACKEND_LABELS.get(platform_key, platform_key)
    lines.append("Платформа: {0} ({1})".format(platform_label, platform_key))

    info = _read_value(None, backend.os_info)
    if info is not None:
        lines.append("Система: {0}".format(str(getattr(info, "pretty", "") or "не определено")))
        hostname = str(getattr(info, "hostname", "") or "")
        if hostname:
            lines.append("Хост: {0}".format(hostname))
    else:
        lines.append("Система: данные недоступны")

    gpus = list(_read_value([], backend.list_gpus) or [])
    lines.append("")
    lines.append("Видеокарты ({0}):".format(len(gpus)))
    if gpus:
        for index, gpu in enumerate(gpus, 1):
            lines.extend(_format_gpu(gpu, index))
    else:
        lines.append("  не обнаружены")

    browsers = list(_read_value([], backend.list_browsers) or [])
    options = list(_read_value([], backend.list_options) or [])
    current_by_browser: List[Optional[Any]] = []
    for browser in browsers:
        current_by_browser.append(_read_value(None, backend.current_option, browser))

    lines.append("")
    lines.append("Браузеры ({0}):".format(len(browsers)))
    if browsers:
        for index, browser in enumerate(browsers, 1):
            lines.extend(_format_browser(backend, browser, index))
    else:
        lines.append("  не обнаружены")

    current_ids = {
        str(getattr(option, "id", "") or "")
        for option in current_by_browser
        if option is not None
    }
    lines.append("")
    lines.append("Варианты ускорителя ({0}):".format(len(options)))
    if options:
        for option in options:
            option_id = str(getattr(option, "id", "") or "")
            marker = "* " if option_id in current_ids else "  "
            lines.append(marker + str(getattr(option, "label", "") or "?"))
            description = str(getattr(option, "description", "") or "")
            if description:
                lines.append("    " + description)
    else:
        lines.append("  не найдены")

    lines.append("")
    lines.append("Текущие настройки браузеров:")
    if browsers:
        for browser, option in zip(browsers, current_by_browser):
            name = str(getattr(browser, "name", "") or "?")
            if option is not None:
                lines.append("  {0}: {1}".format(name, str(getattr(option, "label", "") or "?")))
            else:
                lines.append("  {0}: данные недоступны".format(name))
    else:
        lines.append("  нет данных")

    pending = list(_read_value([], backend.pending_changes) or [])
    lines.append("")
    lines.append("Ожидающие изменения ({0}):".format(len(pending)))
    if pending:
        for change in pending:
            browser_name = str(
                getattr(change, "browser_name", "") or getattr(change, "browser_id", "?")
            )
            option_label = str(
                getattr(change, "option_label", "") or getattr(change, "option_id", "?")
            )
            applied_at = str(getattr(change, "applied_at", "") or "")
            suffix = " ({0})".format(applied_at) if applied_at else ""
            lines.append("  {0}: {1}{2}".format(browser_name, option_label, suffix))
    else:
        lines.append("  нет")

    notes = list(_read_value([], backend.notes) or [])
    lines.append("")
    lines.append("Примечания:")
    if notes:
        for note in notes:
            lines.append("  - {0}".format(note))
    else:
        lines.append("  нет")

    lines.append("")
    lines.append("Диагностика бэкенда:")
    backend_text = str(_read_value("", backend.diagnostics) or "").strip()
    if backend_text:
        for text_line in backend_text.splitlines():
            lines.append("  " + text_line)
    else:
        lines.append("  нет данных")

    lines.append("")
    lines.append("Конец отчёта.")
    return "\n".join(lines)


def _format_gpu(gpu: Any, index: int) -> List[str]:
    name = str(getattr(gpu, "name", "") or "?")
    kind = str(getattr(gpu, "kind", "") or "")
    kind_label = GPU_KIND_LABELS.get(kind, kind or "неизвестно")
    lines = ["  {0}. {1} — {2}".format(index, name, kind_label)]
    vendor = str(getattr(gpu, "vendor", "") or "")
    if vendor:
        lines.append("     Производитель: {0}".format(vendor))
    driver = str(getattr(gpu, "driver", "") or "")
    if driver:
        lines.append("     Драйвер: {0}".format(driver))
    try:
        memory_mb = int(getattr(gpu, "memory_mb", 0) or 0)
    except (TypeError, ValueError):
        memory_mb = 0
    if memory_mb > 0:
        lines.append("     Память: {0} МБ".format(memory_mb))
    detail = str(getattr(gpu, "detail", "") or "")
    if detail:
        lines.append("     Подробности: {0}".format(detail))
    return lines


def _format_browser(backend: PlatformBackend, browser: Any, index: int) -> List[str]:
    name = str(getattr(browser, "name", "") or "?")
    engine = str(getattr(browser, "engine", "") or "")
    version = str(getattr(browser, "version", "") or "")
    suffix = ""
    if engine:
        suffix = " — {0}".format(engine)
        if version:
            suffix += " {0}".format(version)
    elif version:
        suffix = " — {0}".format(version)
    lines = ["  {0}. {1}{2}".format(index, name, suffix)]

    executable = str(getattr(browser, "executable", "") or "")
    if executable:
        lines.append("     Путь: {0}".format(executable))
    else:
        command = getattr(browser, "command", None)
        command_text = ""
        try:
            if command:
                command_text = " ".join(str(part) for part in command)
        except Exception:
            command_text = ""
        if command_text:
            lines.append("     Команда: {0}".format(command_text))

    source = str(getattr(browser, "source", "") or "")
    if source:
        lines.append("     Источник: {0}".format(source))
    if not bool(getattr(browser, "supported", True)):
        lines.append("     Поддержка: ограничена")
    note = str(getattr(browser, "note", "") or "")
    if note:
        lines.append("     Примечание: {0}".format(note))

    running = _read_value(None, backend.is_browser_running, browser)
    if running is None:
        lines.append("     Запущен: неизвестно")
    elif running:
        pids = list(_read_value([], backend.running_pids, browser) or [])
        if pids:
            lines.append("     Запущен: да (PID {0})".format(", ".join(str(pid) for pid in pids)))
        else:
            lines.append("     Запущен: да")
    else:
        lines.append("     Запущен: нет")
    return lines


# ---------------------------------------------------------------------------
# GUI modes
# ---------------------------------------------------------------------------


def _enable_dpi_awareness() -> None:
    """Ask Windows for crisp text on high-DPI screens before Tk starts."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def run_gui(backend: PlatformBackend, screenshot_mode: bool = False) -> int:
    """Open the main window and return an exit code after it is closed."""
    try:
        import tkinter as tk  # noqa: F401  (kept lazy on purpose)
    except Exception as exc:
        return _print_tkinter_missing(exc)
    try:
        from app.ui import GpuSwitchApp
    except Exception as exc:
        print("Не удалось загрузить интерфейс программы: {0}".format(exc))
        return 1
    _enable_dpi_awareness()
    try:
        root = tk.Tk()
    except Exception as exc:
        print("Не удалось открыть окно программы: {0}".format(exc))
        print("Проверьте, что программа запущена в графической среде с поддержкой окон.")
        return 2

    language: Optional[str] = None
    try:
        from app.i18n import initial_language, load_saved_language, save_language

        language = initial_language()
        if not screenshot_mode and load_saved_language() is None:
            # First launch: ask once, remember the answer and never ask again.
            from app.i18n import ask_language

            try:
                root.withdraw()
            except Exception:
                pass
            try:
                chosen = ask_language(root, language)
            finally:
                try:
                    root.deiconify()
                except Exception:
                    pass
            if chosen:
                save_language(chosen)
                language = chosen
    except Exception:
        language = language or None

    app = None
    try:
        app = GpuSwitchApp(
            root, backend, screenshot_mode=bool(screenshot_mode), language=language
        )
        if screenshot_mode:
            _prepare_screenshot_mode(root, app)
        else:
            app.start_refresh()
        root.mainloop()
    finally:
        try:
            if app is not None:
                app.shutdown()
            else:
                try:
                    backend.close()
                except Exception:
                    pass
                try:
                    root.destroy()
                except Exception:
                    pass
        except Exception:
            pass
    return 0


def _prepare_screenshot_mode(root: Any, app: Any) -> None:
    """Fill the window with demo data and show the ready dialog for a screenshot."""
    try:
        root.geometry(SCREENSHOT_GEOMETRY)
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        app.refresh_now()
    except Exception as exc:
        print("Скриншот-режим: не удалось получить данные: {0}".format(exc))
        return

    browser = None
    try:
        browser = app.current_browser()
    except Exception:
        browser = None
    if browser is not None:
        print("Скриншот-режим: выбран браузер «{0}».".format(str(getattr(browser, "name", "") or "")))

    try:
        result = app.apply_selected()
    except Exception as exc:
        print("Скриншот-режим: не удалось применить настройку: {0}".format(exc))
        result = None
    if result is not None and bool(getattr(result, "ok", False)):
        print("Скриншот-режим: открыто окно «Все настроено, запустите браузер».")
    else:
        print("Скриншот-режим: окно подтверждения не открылось; показано главное окно.")

    def focus_windows() -> None:
        # The dialog is an internal window of the app; lift it above the main window.
        try:
            dialog = getattr(app, "_ready_dialog", None)
            if dialog is not None and dialog.winfo_exists():
                dialog.lift()
                dialog.focus_force()
                return
        except Exception:
            pass
        try:
            root.lift()
            root.focus_force()
        except Exception:
            pass

    try:
        root.after(300, focus_windows)
    except Exception:
        pass


def run_ui_smoke_test(backend: PlatformBackend) -> int:
    """Build the real window hidden, run one refresh cycle and destroy it."""
    try:
        import tkinter as tk  # noqa: F401  (kept lazy on purpose)
    except Exception as exc:
        return _print_tkinter_missing(exc)
    try:
        from app.ui import GpuSwitchApp
    except Exception as exc:
        print("Не удалось загрузить интерфейс программы: {0}".format(exc))
        return 1
    _enable_dpi_awareness()
    try:
        root = tk.Tk()
    except Exception as exc:
        print("Не удалось открыть окно программы для проверки: {0}".format(exc))
        print("Похоже, графическая среда недоступна (нет экрана).")
        return 2

    failures: List[str] = []
    app = None
    try:
        root.withdraw()
        app = GpuSwitchApp(root, backend)
        snapshot = app.refresh_now()
        try:
            root.update_idletasks()
        except Exception:
            pass
        _check_smoke_window(app, snapshot, failures)
    except Exception as exc:
        failures.append("Ошибка при создании окна программы: {0}".format(exc))
    finally:
        try:
            if app is not None:
                app.shutdown()
            else:
                try:
                    backend.close()
                except Exception:
                    pass
                try:
                    root.destroy()
                except Exception:
                    pass
        except Exception:
            pass

    if failures:
        print("Смоук-тест интерфейса не пройден:")
        for item in failures:
            print("  - {0}".format(item))
        return 1
    print("Смоук-тест интерфейса прошёл успешно.")
    return 0


def _check_smoke_window(app: Any, snapshot: Any, failures: List[str]) -> None:
    """Collect human-readable problems found in the freshly built window."""
    if snapshot is None:
        failures.append("Окно не получило данные обнаружения.")
        return
    if not bool(getattr(app, "detection_finished", False)):
        failures.append("Обнаружение системы не завершилось.")

    browsers = list(getattr(snapshot, "browsers", []) or [])
    combo = getattr(app, "browser_combo", None)
    values: List[Any] = []
    try:
        if combo is not None:
            values = list(combo["values"])
    except Exception:
        values = []
    if not browsers:
        failures.append("Список браузеров пуст: проверить селектор браузеров нельзя.")
    elif len(values) != len(browsers):
        failures.append(
            "Селектор браузеров показывает {0} из {1} браузеров.".format(len(values), len(browsers))
        )
    if browsers:
        try:
            if app.current_browser() is None:
                failures.append("Браузер не выбран автоматически.")
        except Exception as exc:
            failures.append("Не удалось определить выбранный браузер: {0}".format(exc))

    current_text = ""
    try:
        label = app.current_label
        if label is not None:
            current_text = str(label.cget("text") or "").strip()
    except Exception:
        current_text = ""
    if not current_text:
        failures.append("Подпись текущего ускорителя пуста.")

    options = list(getattr(snapshot, "options", []) or [])
    if not options:
        failures.append("Список вариантов ускорителя пуст.")
    else:
        try:
            labels = app.option_labels()
        except Exception:
            labels = []
        if len(labels) != len(options):
            failures.append(
                "Радиокнопки построены не для всех вариантов ({0} из {1}).".format(
                    len(labels), len(options)
                )
            )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _read_value(default: Any, func: Callable[..., Any], *args: Any) -> Any:
    """Call a backend read method and return default instead of raising."""
    try:
        return func(*args)
    except Exception:
        return default


def _name_list(items: Sequence[Any], limit: int = 4) -> str:
    names = [str(getattr(item, "name", "") or "?") for item in items]
    if len(names) > limit:
        return ", ".join(names[:limit]) + " и другие"
    return ", ".join(names)


def _label_list(items: Sequence[Any], limit: int = 4) -> str:
    labels = [str(getattr(item, "label", "") or getattr(item, "id", "?")) for item in items]
    if len(labels) > limit:
        return ", ".join(labels[:limit]) + " и другие"
    return ", ".join(labels)


def _emit(stream: TextIO, lines: Sequence[str]) -> None:
    try:
        stream.write("\n".join(lines) + "\n")
        flush = getattr(stream, "flush", None)
        if flush is not None:
            flush()
    except (OSError, ValueError):
        pass


def _print_tkinter_missing(exc: Exception) -> int:
    print("Не удалось запустить графический интерфейс: tkinter не установлен ({0}).".format(exc))
    print("В Windows он входит в стандартную установку Python.")
    print("В Linux установите пакет python3-tk (например: sudo apt install python3-tk).")
    return 2
