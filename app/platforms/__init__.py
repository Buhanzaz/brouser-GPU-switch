"""Platform backend factory.

The concrete backends are imported lazily so that this package (and the mock
backend) can be imported on every OS - even though app.platforms.windows uses
winreg and app.platforms.linux reads /proc.
"""

from __future__ import annotations

import sys
from typing import Optional

from app.interface import LINUX, MOCK, WINDOWS, PlatformBackend, UnsupportedPlatformError

__all__ = ["get_backend", "current_platform_key"]


def current_platform_key() -> str:
    """Return the backend key matching the current OS (windows/linux)."""
    if sys.platform.startswith("win"):
        return WINDOWS
    if sys.platform.startswith("linux"):
        return LINUX
    return sys.platform


def get_backend(name: Optional[str] = None) -> PlatformBackend:
    """Create the backend for name (default: auto-detect the OS)."""
    key = (name or current_platform_key()).strip().lower()

    if key in (MOCK, "demo"):
        from app.platforms.mock import MockBackend

        return MockBackend()

    if key == WINDOWS:
        from app.platforms.windows import WindowsBackend

        return WindowsBackend()

    if key == LINUX:
        from app.platforms.linux import LinuxBackend

        return LinuxBackend()

    raise UnsupportedPlatformError(
        "Платформа не поддерживается: " + str(key) + ". Поддерживаются Windows и Linux."
    )
