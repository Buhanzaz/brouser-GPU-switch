"""Developer helper: open the window with release-looking data for screenshots.

Not part of the product.  Writes the client-area geometry of the main window to
``devshots/shots.log`` so a companion PowerShell snippet can capture the pixels.

    python devshots/shots.py main
    python devshots/shots.py success
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.interface import ApplyResult, OsInfo  # noqa: E402
from app.platforms.mock import MockBackend  # noqa: E402
from app.ui import GpuSwitchApp  # noqa: E402

WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 860
LOG = ROOT / "devshots" / "shots.log"


class ScreenshotBackend(MockBackend):
    """Mock data behind a normal Windows system strip (no demo wording)."""

    def os_info(self) -> OsInfo:
        return OsInfo(
            platform_key="windows",
            name="Windows 11",
            version="10.0.22631",
            arch="AMD64",
            hostname="DESKTOP-8FJ2K",
        )

    def apply(self, browser, option) -> ApplyResult:
        result = super().apply(browser, option)
        if not result.ok:
            return result
        return ApplyResult.success("Настройка сохранена: " + option.label)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "main"
    root = tk.Tk()
    root.title("GPU Switch")
    app = GpuSwitchApp(root, ScreenshotBackend())
    root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+40+20")

    app.refresh_now()
    if mode == "success":
        app.apply_selected()

    root.attributes("-topmost", True)
    root.update_idletasks()
    root.update()
    root.after(400, lambda: _log_geometry(root, app))
    root.mainloop()
    return 0


def _log_geometry(root: tk.Tk, app: GpuSwitchApp) -> None:
    try:
        x = root.winfo_rootx()
        y = root.winfo_rooty()
        width = root.winfo_width()
        height = root.winfo_height()
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text(f"{x} {y} {width} {height}\n", encoding="utf-8")
        print(f"READY {x} {y} {width} {height}", flush=True)
    except Exception as exc:  # pragma: no cover - developer helper
        print(f"ERROR {exc}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
