#!/usr/bin/env python3
"""GPU Switch — запуск программы и режимов командной строки.

Без ключей открывается главное окно.  Режимы: самопроверка, диагностика,
смоук-тест интерфейса и скриншот-режим.  Все сообщения — по-русски.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser (kept here: main.py is the CLI entry)."""
    parser = argparse.ArgumentParser(
        description="GPU Switch — переключение графического ускорителя для браузера.",
        epilog=(
            "Без ключей программа открывает окно. Ключи --self-test, --diagnostics, "
            "--ui-smoke-test и --screenshot-mode задают служебный режим работы."
        ),
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--self-test",
        action="store_true",
        help="выполнить самопроверку программы и выйти",
    )
    modes.add_argument(
        "--diagnostics",
        action="store_true",
        help="показать отчёт о системе, видеокартах, браузерах и настройках",
    )
    modes.add_argument(
        "--ui-smoke-test",
        action="store_true",
        help="проверить, что окно программы создаётся и обновляется, не показывая его",
    )
    modes.add_argument(
        "--screenshot-mode",
        action="store_true",
        help="открыть окно с демонстрационными данными для снимка экрана",
    )

    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--mock",
        action="store_true",
        help="использовать демонстрационные данные вместо реальной системы",
    )
    source.add_argument(
        "--platform",
        choices=("windows", "linux", "mock"),
        help="выбрать платформу вручную: windows, linux или mock",
    )
    return parser


# ---------------------------------------------------------------------------
# Packaged (PyInstaller) build support
# ---------------------------------------------------------------------------


def _attach_console_for_command_line_modes() -> None:
    """Print command-line reports from the packaged, console-less exe.

    The single-file build is a windowed (GUI-subsystem) program, so Windows
    never creates a console window - a double-click opens only the program
    window.  In a command-line mode (``--self-test``, ``--diagnostics``, ...)
    the process attaches to the console of the shell it was started from and
    reopens stdout/stderr on it.  When the output is already redirected to a
    file or a pipe, the inherited handles are used unchanged.

    Known Windows limitation: the shell does not wait for a GUI-subsystem
    program, so its prompt can come back before the report is printed.
    Redirecting to a file (``BrouserGPUSwitch.exe --diagnostics > report.txt``)
    avoids the interleaving.
    """
    if not getattr(sys, "frozen", False):
        return
    if len(sys.argv) <= 1:  # GUI mode: no console window at all
        return
    if not sys.platform.startswith("win"):
        return
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if not kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
            return
        try:
            kernel32.SetConsoleOutputCP(65001)  # UTF-8, for the Russian report
        except Exception:
            pass
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
    except Exception:
        pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the app and return its exit code."""
    _attach_console_for_command_line_modes()
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    from app.main import run

    try:
        return int(run(args))
    except KeyboardInterrupt:
        print("Работа программы прервана пользователем.")
        return 130
    except Exception as exc:
        print("Не удалось выполнить программу: {0}".format(exc))
        print("Подсказка: запустите «python main.py --diagnostics», чтобы получить отчёт о системе.")
        return 1


def _configure_stdio() -> None:
    """Make Russian text print correctly when output is redirected on Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                continue
            encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if encoding == "utf8":
                continue
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
