"""Tkinter user interface for GPU Switch.

The window is a thin shell around a PlatformBackend implementation from
app.interface: it never touches the registry, sysfs or processes directly.
User-visible strings come from app/i18n.py: the window is available in five
languages and Russian is the default.

Detection runs in a background thread so the window stays responsive; the
worker only performs read-only backend calls and delivers a DetectionSnapshot
through a queue that the Tk main loop drains with after(). Every mutating call
(apply / restore / launch) happens on the Tk main thread while detection is not
running, which keeps a single-threaded backend contract intact.
"""
from __future__ import annotations

import datetime
import queue
import threading
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app import theme as theme_module
from app.i18n import (
    LANGUAGES,
    TRANSLATIONS,
    Translator,
    language_name,
    save_language,
    translate_option_description,
    translate_option_label,
)
from app.interface import (
    APP_NAME,
    APP_VERSION,
    ApplyResult,
    Browser,
    Gpu,
    GpuOption,
    OsInfo,
    PendingChange,
    PlatformBackend,
)

# ---------------------------------------------------------------------------
# UI text. The Russian strings live in app/i18n.py and double as the canonical
# product wording (the tests assert them); the other four languages are
# resolved through Translator when the window is built.
# ---------------------------------------------------------------------------

_RU = TRANSLATIONS["ru"]

WINDOW_TITLE = "GPU Switch"
HEADER_TITLE = "GPU Switch"
HEADER_SUBTITLE = _RU["subtitle"]

SYSTEM_SECTION = _RU["system"]
GPUS_SECTION = _RU["gpus"]
BROWSER_SECTION = _RU["browser"]
BROWSER_PROMPT = _RU["browser_prompt"]
CURRENT_PREFIX = _RU["current_prefix"]
CURRENT_DEFAULT_NOTE = _RU["current_default_note"]
OPTIONS_SECTION = _RU["options"]
APPLY_BUTTON = _RU["apply"]
RUNNING_WARNING = _RU["running_warning"]
CHECK_AGAIN_BUTTON = _RU["check_again"]
RESTORE_ALL_BUTTON = _RU["restore_all"]
RESTORE_BROWSER_BUTTON = _RU["restore_browser"]
PENDING_SECTION = _RU["pending_section"]
PENDING_EMPTY = _RU["pending_empty"]
PENDING_HEADERS = (
    _RU["pending_header_browser"],
    _RU["pending_header_option"],
    _RU["pending_header_when"],
)
GPU_HEADERS = (
    _RU["gpu_header_name"],
    _RU["gpu_header_kind"],
    _RU["gpu_header_driver"],
)
NOT_FOUND = _RU["not_found"]
BROWSERS_SUMMARY_PREFIX = "Обнаружено браузеров:"
NO_BROWSERS_SUMMARY = _RU["no_browsers_summary"]

READY_TITLE = _RU["ready_title"]
READY_DETAIL = _RU["ready_detail"]
READY_HINT = _RU["ready_hint"]
READY_WARNINGS_PREFIX = _RU["ready_warnings_prefix"]
LAUNCH_BUTTON = _RU["launch"]
CLOSE_BUTTON = _RU["close"]
LAUNCH_DIALOG_TITLE = _RU["launch_dialog_title"]

RESTORE_ALL_TITLE = _RU["restore_all_title"]
RESTORE_ALL_CONFIRM = _RU["restore_all_confirm"]
RESTORE_BROWSER_TITLE = _RU["restore_browser_title"]
RESTORE_BROWSER_CONFIRM = _RU["restore_browser_confirm"]
RESTORE_DONE_TITLE = _RU["restore_done_title"]

STATUS_DETECTING = _RU["status_detecting"]
STATUS_DETECTED = _RU["status_detected"]
STATUS_DETECTED_PROBLEMS = _RU["status_detected_problems"]
STATUS_CHECKING = _RU["status_checking"]
STATUS_CHECK_RUNNING = _RU["status_check_running"]
STATUS_CHECK_STOPPED = _RU["status_check_stopped"]
STATUS_NO_BROWSER = _RU["status_no_browser"]
STATUS_NO_OPTION = _RU["status_no_option"]
STATUS_APPLY_FAILED = _RU["status_apply_failed"]
STATUS_RESTORE_FAILED = _RU["status_restore_failed"]
STATUS_RESTORE_EMPTY = _RU["status_restore_empty"]
STATUS_LAUNCH_FAILED = _RU["status_launch_failed"]

PLATFORM_LABELS = {
    "mock": _RU["platform_mock"],
    "demo": _RU["platform_mock"],
    "windows": "Windows",
    "linux": "Linux",
}
GPU_KIND_LABELS = {
    "integrated": _RU["gpu_integrated"],
    "discrete": _RU["gpu_discrete"],
    "virtual": _RU["gpu_virtual"],
    "unknown": _RU["gpu_unknown"],
}
GPU_VENDOR_LABELS = {
    "nvidia": "NVIDIA",
    "amd": "AMD",
    "intel": "Intel",
    "microsoft": "Microsoft",
    "virtual": _RU["gpu_virtual"],
    "other": "",
}

DETECTION_POLL_MS = 40
DEFAULT_WIDTH = 1000
DEFAULT_HEIGHT = 860
MIN_WIDTH = 880
MIN_HEIGHT = 640

PLACEHOLDER_ROW_TAG = "placeholder"

INFO = "info"
OK = "ok"
ERROR = "error"

_STATUS_STYLES = {
    INFO: "Status.TLabel",
    OK: "StatusOk.TLabel",
    ERROR: "StatusError.TLabel",
}


@dataclass
class DetectionSnapshot:
    """Everything the window displays, collected in one read-only pass."""

    os_info: Optional[OsInfo] = None
    gpus: List[Gpu] = field(default_factory=list)
    browsers: List[Browser] = field(default_factory=list)
    options: List[GpuOption] = field(default_factory=list)
    current: Dict[str, GpuOption] = field(default_factory=dict)
    running: Dict[str, bool] = field(default_factory=dict)
    pids: Dict[str, List[int]] = field(default_factory=dict)
    pending: List[PendingChange] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)


class GpuSwitchApp:
    """Main window of GPU Switch.

    The class is intentionally explicit about its public surface: the CLI and
    the smoke tests need to drive it without a running event loop.
    """

    def __init__(
        self,
        root: tk.Tk,
        backend: PlatformBackend,
        screenshot_mode: bool = False,
        language: Optional[str] = None,
    ) -> None:
        self.root = root
        self.backend = backend
        self.screenshot_mode = bool(screenshot_mode)
        self.translator = Translator(language)
        self.language = self.translator.language
        self.tr = self.translator.t

        self._snapshot: Optional[DetectionSnapshot] = None
        self._busy = False
        self._closing = False
        self._shutdown_done = False
        self._poll_id: Optional[str] = None
        self._worker: Optional[threading.Thread] = None
        self._queue: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self._screenshot_prepared = False
        self._ready_dialog: Optional[tk.Toplevel] = None
        self._grab_after_id: Optional[str] = None
        self._body_sync_id: Optional[str] = None
        # Selection kept across an in-place language change so the user keeps
        # working with the same browser and accelerator.
        self._restore_browser_id: str = ""
        self._restore_option_id: str = ""

        # Hooks that tests (and future automation) may replace.
        self.confirm: Callable[[str, str], bool] = self._ask_confirm
        self.notify: Callable[[str, str], None] = self._show_info

        self._option_var = tk.StringVar(master=root, value="")
        self._option_radio_by_id: Dict[str, ttk.Radiobutton] = {}
        self._pending_placeholder_item: Optional[str] = None
        self._current_note_shown = False
        self._running_warning_shown = False
        self._restore_browser_shown = False

        self._setup_style()
        self._configure_window()
        self._build_ui()
        self._bind_shortcuts()
        self._set_status("", INFO)

    # ------------------------------------------------------------------
    # Window / theme setup
    # ------------------------------------------------------------------
    def _configure_window(self) -> None:
        self.root.title(WINDOW_TITLE)
        scale = self.theme.scale
        try:
            self.root.minsize(int(MIN_WIDTH * scale), int(MIN_HEIGHT * scale))
        except tk.TclError:
            pass
        if not self.screenshot_mode:
            try:
                screen_w = self.root.winfo_screenwidth()
                screen_h = self.root.winfo_screenheight()
                width = int(
                    min(DEFAULT_WIDTH * scale, max(MIN_WIDTH * scale, screen_w - int(80 * scale)))
                )
                height = int(
                    min(DEFAULT_HEIGHT * scale, max(MIN_HEIGHT * scale, screen_h - int(120 * scale)))
                )
                x = max(0, (screen_w - width) // 2)
                y = max(0, (screen_h - height) // 2)
                self.root.geometry(f"{width}x{height}+{x}+{y}")
            except tk.TclError:
                pass
        try:
            scaling = self.root.winfo_fpixels("1i") / 72.0
            scaling = max(1.0, min(4.0, scaling))
            self.root.tk.call("tk", "scaling", scaling)
        except tk.TclError:
            pass
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _setup_style(self) -> None:
        """Install the Windows 11 (Fluent) style set; see app/theme.py."""
        self.theme = theme_module.apply(self.root)
        self.style = self.theme.style
        self._background = self.theme.colors["page"]

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        px = self.theme.px
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        page = ttk.Frame(self.root, style="Page.TFrame")
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            page,
            highlightthickness=0,
            borderwidth=0,
            background=self._background,
            yscrollincrement=px(20),
        )
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar = theme_module.ThinScrollbar(
            page,
            command=self._canvas.yview,
            width=px(12),
            background=self._background,
            thumb=self.theme.colors["scroll_thumb"],
            thumb_active=self.theme.colors["scroll_thumb_hover"],
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        self._scrollbar.grid_remove()

        body = ttk.Frame(
            self._canvas,
            style="Page.TFrame",
            padding=(px(24), px(20), px(24), px(16)),
        )
        self._body = body
        self._canvas_window = self._canvas.create_window((0, 0), window=body, anchor="nw")
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        body.bind("<Configure>", self._on_body_configure)
        body.columnconfigure(0, weight=1)

        self._build_header(body)
        self._build_system_section(body)
        self._build_gpus_section(body)
        self._build_browser_section(body)
        self._build_options_section(body)
        self._build_pending_section(body)
        self._build_actions()
        self._build_status_bar()

    def _build_header(self, parent: ttk.Frame) -> None:
        px = self.theme.px
        header = ttk.Frame(parent, style="Page.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, px(10)))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=HEADER_TITLE, style="Title.TLabel", anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, text=self.tr("subtitle"), style="Subtitle.TLabel", anchor="w").grid(
            row=1, column=0, sticky="w", pady=(px(2), 0)
        )
        ttk.Label(
            header,
            text=self.tr("version_label", version=APP_VERSION),
            style="Version.TLabel",
            anchor="e",
        ).grid(row=0, column=1, sticky="e")
        self.language_combo = ttk.Combobox(
            header,
            state="readonly",
            width=12,
            values=[name for _code, name in LANGUAGES],
            style="Browser.TCombobox",
        )
        self.language_combo.set(language_name(self.language))
        self.language_combo.grid(row=1, column=1, sticky="e", pady=(px(2), 0))
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_selected)

    def _on_language_selected(self, _event: Optional["tk.Event[Any]"] = None) -> None:
        """Store the picked language and rebuild the window in place."""
        try:
            name = str(self.language_combo.get())
        except tk.TclError:
            return
        code = next((item for item, label in LANGUAGES if label == name), None)
        if not code or code == self.language:
            return
        save_language(code)
        self._switch_language(code)

    def _switch_language(self, code: str) -> None:
        """Rebuild every widget in ``code`` without restarting the process.

        Rewriting the interface in place keeps the program responsive and
        avoids re-executing the frozen executable (which on locked-down
        machines can fail while unpacking its temporary directories).
        """
        browser_id = ""
        browser = self.current_browser()
        if browser is not None:
            browser_id = browser.id
        option_id = ""
        try:
            option_id = str(self._option_var.get())
        except tk.TclError:
            option_id = ""

        self._cancel_poll()
        self.close_ready_dialog()
        for child in list(self.root.winfo_children()):
            child.destroy()

        self.translator = Translator(code)
        self.language = self.translator.language
        self.tr = self.translator.t
        self._snapshot = None
        self._busy = False
        self._body_sync_id = None
        self._pending_placeholder_item = None
        self._current_note_shown = False
        self._running_warning_shown = False
        self._restore_browser_shown = False
        self._option_radio_by_id = {}
        self._restore_browser_id = browser_id
        self._restore_option_id = option_id
        try:
            self._option_var = tk.StringVar(master=self.root, value=option_id)
        except tk.TclError:
            return

        self._build_ui()
        self._set_status("", INFO)
        self.start_refresh()

    def _build_system_section(self, parent: ttk.Frame) -> None:
        px = self.theme.px
        strip = ttk.Frame(parent, style="Strip.TFrame", padding=(px(16), px(8), px(16), px(8)))
        strip.grid(row=1, column=0, sticky="ew", pady=(0, px(8)))
        strip.columnconfigure(1, weight=1)
        ttk.Label(strip, text=self.tr("system"), style="SystemCaption.TLabel", anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, px(12))
        )
        self.system_label = ttk.Label(
            strip,
            text=self.tr("status_detecting"),
            style="SystemLabel.TLabel",
            anchor="w",
            justify="left",
        )
        self.system_label.grid(row=0, column=1, sticky="ew")

    def _build_gpus_section(self, parent: ttk.Frame) -> None:
        px = self.theme.px
        card = self.theme.card(parent)
        card.grid(row=2, column=0, sticky="ew", pady=(0, px(8)))
        card.columnconfigure(0, weight=1)

        head = ttk.Frame(card, style="CardBody.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, px(8)))
        head.columnconfigure(0, weight=1)
        self.theme.section_title(head, self.tr("gpus")).grid(row=0, column=0, sticky="w")
        self.gpu_count_label = ttk.Label(head, text="", style="CardHint.TLabel", anchor="e")
        self.gpu_count_label.grid(row=0, column=1, sticky="e")

        host = ttk.Frame(card, style="CardBody.TFrame")
        host.grid(row=1, column=0, sticky="ew")
        host.columnconfigure(0, weight=1)

        self.gpu_tree = ttk.Treeview(
            host,
            columns=("name", "kind", "driver"),
            show="headings",
            height=2,
            selectmode="none",
            style="Fluent.Treeview",
        )
        self.gpu_tree.heading("name", text=self.tr("gpu_header_name"), anchor="w")
        self.gpu_tree.heading("kind", text=self.tr("gpu_header_kind"), anchor="w")
        self.gpu_tree.heading("driver", text=self.tr("gpu_header_driver"), anchor="w")
        self.gpu_tree.column("name", width=px(420), minwidth=px(240), stretch=True, anchor="w")
        self.gpu_tree.column("kind", width=px(240), minwidth=px(140), stretch=False, anchor="w")
        self.gpu_tree.column("driver", width=px(240), minwidth=px(120), stretch=False, anchor="w")
        self.gpu_tree.grid(row=0, column=0, sticky="ew")
        self._gpu_scroll = theme_module.ThinScrollbar(
            host,
            command=self.gpu_tree.yview,
            width=px(10),
            background=self.theme.colors["card"],
            thumb=self.theme.colors["scroll_thumb"],
            thumb_active=self.theme.colors["scroll_thumb_hover"],
        )
        self.gpu_tree.configure(yscrollcommand=self._gpu_scroll.set)
        self._gpu_scroll.grid(row=0, column=1, sticky="ns")
        self._gpu_scroll.grid_remove()
        self.gpu_tree.tag_configure(PLACEHOLDER_ROW_TAG, foreground=self.theme.colors["text3"])

    def _build_browser_section(self, parent: ttk.Frame) -> None:
        px = self.theme.px
        card = self.theme.card(parent)
        card.grid(row=3, column=0, sticky="ew", pady=(0, px(8)))
        card.columnconfigure(0, weight=1)

        self.theme.section_title(card, self.tr("browser")).grid(row=0, column=0, sticky="w")
        self.browser_prompt_label = ttk.Label(
            card, text=self.tr("browser_prompt"), style="Prompt.TLabel", anchor="w", justify="left"
        )
        self.browser_prompt_label.grid(row=1, column=0, sticky="ew", pady=(px(2), px(4)))

        self.browser_combo = ttk.Combobox(
            card, state="disabled", values=(), width=56, style="Browser.TCombobox"
        )
        self.browser_combo.grid(row=2, column=0, sticky="ew")
        self.browser_combo.bind("<<ComboboxSelected>>", self._on_browser_selected)

        self.browser_summary_label = ttk.Label(
            card, text="", style="CardHint.TLabel", anchor="w", justify="left"
        )
        # Deliberately not gridded: the "Обнаружено браузеров: …" line is hidden
        # in the window (the list is visible in the combobox itself), but the
        # label stays as the empty-state contract used by the tests.
        self.browser_summary_label.grid_remove()

        self.current_frame = ttk.Frame(
            card, style="Current.TFrame", padding=(px(12), px(8), px(12), px(9))
        )
        self.current_frame.grid(row=4, column=0, sticky="ew", pady=(px(8), 0))
        # Hidden per the latest product decision: the current accelerator is
        # already implied by the preselected radio option, and the explicit
        # "Сейчас включён ускоритель" line is not shown in the window.
        self.current_frame.grid_remove()
        self.current_frame.columnconfigure(1, weight=1)
        self._current_rule = tk.Frame(
            self.current_frame,
            background=self.theme.colors["accent"],
            width=px(3),
            borderwidth=0,
            highlightthickness=0,
        )
        self._current_rule.grid(row=0, column=0, sticky="ns", padx=(0, px(10)))
        self.current_label = ttk.Label(
            self.current_frame,
            text=f"{self.tr('current_prefix')} {self.tr('not_found')}",
            style="Current.TLabel",
            anchor="w",
            justify="left",
        )
        self.current_label.grid(row=0, column=1, sticky="ew")

        self.current_note_label = ttk.Label(
            card,
            text=self.tr("current_default_note"),
            style="Hint.TLabel",
            anchor="w",
            justify="left",
        )
        # Hidden per the design review: the default-mode explanation is not
        # shown in the window, but the visibility flag is still tracked.
        self.current_note_label.grid_remove()

        self.running_frame = ttk.Frame(
            card, style="RunningBanner.TFrame", padding=(px(12), px(6), px(12), px(6))
        )
        self.running_frame.grid(row=6, column=0, sticky="ew", pady=(px(10), 0))
        self.running_frame.columnconfigure(0, weight=1)
        self.running_warning_label = ttk.Label(
            self.running_frame,
            text=self.tr("running_warning"),
            style="Warning.TLabel",
            anchor="w",
            justify="left",
        )
        self.running_warning_label.grid(row=0, column=0, sticky="ew", padx=(0, px(12)))
        self.check_again_button = ttk.Button(
            self.running_frame,
            text=self.tr("check_again"),
            style="Small.Secondary.TButton",
            command=self.check_again,
        )
        self.check_again_button.grid(row=0, column=1, sticky="e")
        self.running_frame.grid_remove()

    def _build_options_section(self, parent: ttk.Frame) -> None:
        px = self.theme.px
        card = self.theme.card(parent)
        card.grid(row=4, column=0, sticky="ew", pady=(0, px(8)))
        card.columnconfigure(0, weight=1)
        self.theme.section_title(card, self.tr("options")).grid(
            row=0, column=0, sticky="w", pady=(0, px(4))
        )
        self.options_inner = ttk.Frame(card, style="CardBody.TFrame")
        self.options_inner.grid(row=1, column=0, sticky="ew")
        self.options_inner.columnconfigure(0, weight=1)

    def _build_actions(self) -> None:
        px = self.theme.px
        ttk.Separator(self.root, orient="horizontal").grid(row=1, column=0, sticky="ew")
        bar = ttk.Frame(self.root, style="ActionBar.TFrame", padding=(px(24), px(8)))
        bar.grid(row=2, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)

        self.action_hint_label = ttk.Label(
            bar, text="", style="ActionHint.TLabel", anchor="w", justify="left"
        )
        self.action_hint_label.grid(row=0, column=0, sticky="ew", padx=(0, px(16)))

        self.restore_browser_button = ttk.Button(
            bar,
            text=self.tr("restore_browser"),
            style="Secondary.TButton",
            command=self.restore_selected_browser,
        )
        self.restore_browser_button.grid(row=0, column=1, padx=(0, px(8)))
        self.restore_browser_button.grid_remove()

        self.restore_all_button = ttk.Button(
            bar, text=self.tr("restore_all"), style="Danger.TButton", command=self.restore_all
        )
        self.restore_all_button.grid(row=0, column=2, padx=(0, px(8)))

        self.apply_button = ttk.Button(
            bar, text=self.tr("apply"), style="Accent.TButton", command=self.apply_selected
        )
        self.apply_button.grid(row=0, column=3)
        self.apply_button.state(["disabled"])

    def _build_pending_section(self, parent: ttk.Frame) -> None:
        px = self.theme.px
        card = self.theme.card(parent)
        self._pending_card = card
        card.grid(row=5, column=0, sticky="ew", pady=(0, px(8)))
        card.columnconfigure(0, weight=1)
        card.grid_remove()  # shown only when something has actually changed

        head = ttk.Frame(card, style="CardBody.TFrame")
        head.grid(row=0, column=0, sticky="ew", pady=(0, px(8)))
        head.columnconfigure(0, weight=1)
        self.theme.section_title(head, self.tr("pending_section")).grid(row=0, column=0, sticky="w")
        self.pending_count_label = ttk.Label(head, text="", style="CardHint.TLabel", anchor="e")
        self.pending_count_label.grid(row=0, column=1, sticky="e")

        host = ttk.Frame(card, style="CardBody.TFrame")
        host.grid(row=1, column=0, sticky="ew")
        host.columnconfigure(0, weight=1)

        self.pending_tree = ttk.Treeview(
            host,
            columns=("browser", "option", "when"),
            show="headings",
            height=1,
            selectmode="none",
            style="Fluent.Treeview",
        )
        self.pending_tree.heading("browser", text=self.tr("pending_header_browser"), anchor="w")
        self.pending_tree.heading("option", text=self.tr("pending_header_option"), anchor="w")
        self.pending_tree.heading("when", text=self.tr("pending_header_when"), anchor="w")
        self.pending_tree.column("browser", width=px(260), minwidth=px(160), stretch=True, anchor="w")
        self.pending_tree.column("option", width=px(420), minwidth=px(220), stretch=True, anchor="w")
        self.pending_tree.column("when", width=px(180), minwidth=px(120), stretch=False, anchor="w")
        self.pending_tree.grid(row=0, column=0, sticky="ew")
        self._pending_scroll = theme_module.ThinScrollbar(
            host,
            command=self.pending_tree.yview,
            width=px(10),
            background=self.theme.colors["card"],
            thumb=self.theme.colors["scroll_thumb"],
            thumb_active=self.theme.colors["scroll_thumb_hover"],
        )
        self.pending_tree.configure(yscrollcommand=self._pending_scroll.set)
        self._pending_scroll.grid(row=0, column=1, sticky="ns")
        self._pending_scroll.grid_remove()
        self.pending_tree.tag_configure(PLACEHOLDER_ROW_TAG, foreground=self.theme.colors["text3"])

    def _build_status_bar(self) -> None:
        px = self.theme.px
        ttk.Separator(self.root, orient="horizontal").grid(row=3, column=0, sticky="ew")
        bar = ttk.Frame(self.root, style="StatusBar.TFrame", padding=(px(24), px(6)))
        bar.grid(row=4, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)

        self._status_dot = tk.Canvas(
            bar,
            width=px(10),
            height=px(10),
            background=self.theme.colors["subtle"],
            highlightthickness=0,
            borderwidth=0,
        )
        self._status_dot.grid(row=0, column=0, padx=(0, px(8)))
        self._status_dot_item = self._status_dot.create_oval(
            px(1),
            px(1),
            px(9),
            px(9),
            fill=self.theme.colors["text3"],
            outline="",
        )

        self.status_var = tk.StringVar(master=self.root, value="")
        self.status_label = ttk.Label(
            bar, textvariable=self.status_var, style="Status.TLabel", anchor="w"
        )
        self.status_label.grid(row=0, column=1, sticky="ew")
        ttk.Label(
            bar,
            text=f"{APP_NAME} {APP_VERSION} · {self.tr('status_hint')}",
            style="StatusHint.TLabel",
            anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=(px(12), 0))

    # ------------------------------------------------------------------
    # Geometry helpers: scrollable body + wrapping labels
    # ------------------------------------------------------------------
    def _on_canvas_configure(self, event: "tk.Event[Any]") -> None:
        if self._closing:
            return
        try:
            self._canvas.itemconfigure(
                self._canvas_window,
                width=max(event.width, 1),
                height=max(event.height, self._body.winfo_reqheight()),
            )
        except tk.TclError:
            pass
        self._update_wraplengths()
        self._update_scrollbar()

    def _sync_body_height(self) -> None:
        """Resize the scrollable page after sections are shown or hidden."""
        self._body_sync_id = None
        if self._closing:
            return
        try:
            if not self._canvas.winfo_exists():
                return
            self._canvas.itemconfigure(
                self._canvas_window,
                width=max(self._canvas.winfo_width(), 1),
                height=max(self._canvas.winfo_height(), self._body.winfo_reqheight()),
            )
        except tk.TclError:
            return
        self._on_body_configure(None)

    def _queue_body_sync(self) -> None:
        """Re-run :meth:`_sync_body_height` once Tk has applied the new layout."""
        if self._body_sync_id is not None:
            try:
                self.root.after_cancel(self._body_sync_id)
            except Exception:
                pass
            self._body_sync_id = None
        try:
            self._body_sync_id = self.root.after_idle(self._sync_body_height)
        except tk.TclError:
            self._body_sync_id = None

    def _on_body_configure(self, _event: "tk.Event[Any]") -> None:
        if self._closing:
            return
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except tk.TclError:
            pass
        self._update_scrollbar()

    def _update_scrollbar(self) -> None:
        if self._closing:
            return
        try:
            needed = self._body.winfo_reqheight() > self._canvas.winfo_height()
            shown = bool(self._scrollbar.winfo_manager())
            if needed and not shown:
                self._scrollbar.grid(row=0, column=1, sticky="ns")
            elif not needed and shown:
                self._scrollbar.grid_remove()
        except tk.TclError:
            pass

    def _update_wraplengths(self) -> None:
        try:
            width = max(
                self._body.winfo_width() - self.theme.px(24 + 24 + 16 + 16 + 8),
                self.theme.px(320),
            )
        except tk.TclError:
            return
        for widget in (
            self.system_label,
            self.browser_summary_label,
            self.current_label,
            self.current_note_label,
            self.running_warning_label,
        ):
            try:
                widget.configure(wraplength=width)
            except tk.TclError:
                pass
        try:
            # The "Система" caption shares the row with the value.
            self.system_label.configure(
                wraplength=max(width - self.theme.px(96), self.theme.px(240))
            )
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------
    def _bind_shortcuts(self) -> None:
        self.root.bind("<Escape>", self._on_escape)
        self.root.bind("<F5>", self._on_refresh_key)
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                self.root.bind_all(sequence, self._on_mousewheel, add="+")
            except tk.TclError:  # pragma: no cover - exotic Tk builds
                continue

    def _on_mousewheel(self, event: "tk.Event[Any]") -> None:
        """Scroll the page with the wheel; tables keep their own scrolling."""
        if self._closing:
            return
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        if widget is None:
            return
        node: Optional[Any] = widget
        while node is not None:
            if isinstance(node, ttk.Treeview):
                return
            if node is self._body:
                break
            if node is self.root:
                return
            node = getattr(node, "master", None)
        else:
            return
        try:
            if self._body.winfo_reqheight() <= self._canvas.winfo_height():
                return
            number = getattr(event, "num", 0)
            if number == 4:
                step = -3
            elif number == 5:
                step = 3
            else:
                step = -3 if int(getattr(event, "delta", 0) or 0) > 0 else 3
            self._canvas.yview_scroll(step, "units")
        except tk.TclError:
            pass

    def _on_escape(self, _event: "tk.Event[Any]") -> str:
        if self._ready_dialog is not None and self._dialog_alive():
            self.close_ready_dialog()
        else:
            self.close()
        return "break"

    def _on_refresh_key(self, _event: "tk.Event[Any]") -> str:
        self.start_refresh()
        return "break"

    # ------------------------------------------------------------------
    # Detection (worker thread + queue + after())
    # ------------------------------------------------------------------
    def start_refresh(self) -> None:
        """Start detection in a worker thread without blocking the UI."""
        if self._closing or self._busy:
            return
        self._busy = True
        self._set_status(self.tr("status_detecting"), INFO)
        self._update_action_states()
        self._worker = threading.Thread(
            target=self._detection_worker, name="gpu-switch-detection", daemon=True
        )
        self._worker.start()
        self._schedule_poll()

    def _detection_worker(self) -> None:
        try:
            snapshot = self._detect()
        except Exception as exc:  # pragma: no cover - defensive only
            self._queue.put(("error", f"{exc}"))
            return
        self._queue.put(("snapshot", snapshot))

    def _schedule_poll(self) -> None:
        if self._closing:
            return
        try:
            self._poll_id = self.root.after(DETECTION_POLL_MS, self._poll_queue)
        except tk.TclError:
            self._poll_id = None

    def _poll_queue(self) -> None:
        self._poll_id = None
        if self._closing:
            return
        finished = False
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "snapshot":
                self._apply_snapshot(payload)
                finished = True
            elif kind == "error":
                self._busy = False
                self._set_status(
                    f"{self.tr('status_detected_problems')} {payload}", ERROR
                )
                self._update_action_states()
                finished = True
        if not finished:
            self._schedule_poll()

    def refresh_now(self, status_message: Optional[str] = None, status_kind: str = INFO) -> DetectionSnapshot:
        """Synchronously collect and display state (used by tests and after actions)."""
        self._cancel_poll()
        self._busy = True
        self._update_action_states()
        snapshot = self._detect()
        self._apply_snapshot(snapshot)
        if status_message is not None:
            self._set_status(status_message, status_kind)
        return snapshot

    def _detect(self) -> DetectionSnapshot:
        backend = self.backend
        problems: List[str] = []
        snapshot = DetectionSnapshot()

        snapshot.os_info = self._safe(
            self.tr("problem_system"), backend.os_info, problems, None
        )
        snapshot.gpus = list(
            self._safe(self.tr("problem_gpus"), backend.list_gpus, problems, []) or []
        )
        snapshot.browsers = list(
            self._safe(self.tr("problem_browsers"), backend.list_browsers, problems, []) or []
        )
        snapshot.options = list(
            self._safe(
                self.tr("problem_options"), backend.list_options, problems, []
            )
            or []
        )
        snapshot.pending = list(
            self._safe(
                self.tr("problem_pending"), backend.pending_changes, problems, []
            )
            or []
        )
        snapshot.notes = list(
            self._safe(self.tr("problem_notes"), backend.notes, problems, []) or []
        )

        for browser in snapshot.browsers:
            browser_id = getattr(browser, "id", "")
            current = self._safe(
                self.tr("problem_current"),
                lambda b=browser: backend.current_option(b),
                problems,
                None,
            )
            if current is not None:
                snapshot.current[browser_id] = current
            running = bool(
                self._safe(
                    self.tr("problem_running"),
                    lambda b=browser: backend.is_browser_running(b),
                    problems,
                    False,
                )
            )
            snapshot.running[browser_id] = running
            pids = self._safe(
                self.tr("problem_pids"),
                lambda b=browser: backend.running_pids(b),
                problems,
                [],
            )
            snapshot.pids[browser_id] = list(pids or [])
        return snapshot

    def _safe(
        self,
        label: str,
        func: Callable[[], Any],
        problems: List[str],
        fallback: Any,
    ) -> Any:
        try:
            return func()
        except Exception as exc:
            problems.append(f"{label}: {exc}")
            return fallback

    # ------------------------------------------------------------------
    # Snapshot rendering
    # ------------------------------------------------------------------
    def _apply_snapshot(self, snapshot: DetectionSnapshot) -> None:
        self._snapshot = snapshot
        self._busy = False
        self._populate_system(snapshot)
        self._populate_gpus(snapshot)
        self._populate_options(snapshot)
        self._populate_pending(snapshot)
        self._populate_notes(snapshot)
        self._populate_browsers(snapshot)
        self._on_browser_selected()
        if self._restore_option_id and self._restore_option_id in self._option_radio_by_id:
            self._option_var.set(self._restore_option_id)
        self._restore_option_id = ""
        self._update_action_states()

        if snapshot.problems:
            details = "; ".join(snapshot.problems[:3])
            if len(snapshot.problems) > 3:
                details += " " + self.tr("and_more")
            self._set_status(
                f"{self.tr('status_detected_problems')} {details}", ERROR
            )
        else:
            self._set_status(self._detected_status(snapshot), INFO)

        if self.screenshot_mode and not self._screenshot_prepared:
            self._prepare_screenshot_view(snapshot)

    def _detected_status(self, snapshot: DetectionSnapshot) -> str:
        counts = self.tr(
            "status_detected_counts",
            browsers=len(snapshot.browsers),
            gpus=len(snapshot.gpus),
            options=len(snapshot.options),
        )
        return f"{self.tr('status_detected')} {counts}"

    def _populate_system(self, snapshot: DetectionSnapshot) -> None:
        info = snapshot.os_info
        if info is None:
            self.system_label.configure(text=self.tr("not_found"))
            return
        parts: List[str] = []
        pretty = getattr(info, "pretty", "") or ""
        if pretty:
            parts.append(pretty)
        platform_key = getattr(info, "platform_key", "") or ""
        if platform_key in ("mock", "demo"):
            platform_label = self.tr("platform_mock")
        else:
            platform_label = PLATFORM_LABELS.get(platform_key, platform_key)
        if platform_label:
            parts.append(self.tr("platform", label=platform_label))
        self.system_label.configure(
            text="  ·  ".join(parts) if parts else self.tr("not_found")
        )

    def _populate_gpus(self, snapshot: DetectionSnapshot) -> None:
        for item in self.gpu_tree.get_children(""):
            self.gpu_tree.delete(item)
        if not snapshot.gpus:
            self.gpu_tree.insert(
                "",
                "end",
                values=(self.tr("not_found"), "", ""),
                tags=(PLACEHOLDER_ROW_TAG,),
            )
            try:
                self.gpu_count_label.configure(text="")
            except tk.TclError:
                pass
            self._sync_tree_scrollbar(self.gpu_tree, self._gpu_scroll)
            return
        try:
            self.gpu_count_label.configure(
                text=self.tr("gpu_found", count=len(snapshot.gpus))
            )
        except tk.TclError:
            pass
        for gpu in snapshot.gpus:
            kind_key = str(getattr(gpu, "kind", "") or "")
            if kind_key in ("integrated", "discrete", "virtual"):
                kind = self.tr("gpu_" + kind_key)
            else:
                kind = kind_key or self.tr("gpu_unknown")
            vendor_key = str(getattr(gpu, "vendor", "") or "")
            if vendor_key == "virtual":
                vendor = self.tr("gpu_virtual")
            else:
                vendor = GPU_VENDOR_LABELS.get(vendor_key, "")
            kind_text = f"{kind} ({vendor})" if vendor else kind
            self.gpu_tree.insert(
                "",
                "end",
                values=(
                    getattr(gpu, "name", "") or self.tr("not_found"),
                    kind_text,
                    getattr(gpu, "driver", "") or "—",
                ),
            )
        self._sync_tree_scrollbar(self.gpu_tree, self._gpu_scroll)

    def _populate_options(self, snapshot: DetectionSnapshot) -> None:
        px = self.theme.px
        for child in self.options_inner.winfo_children():
            child.destroy()
        self._option_radio_by_id = {}
        if not snapshot.options:
            self.options_empty_label = ttk.Label(
                self.options_inner, text=self.tr("not_found"), style="Hint.TLabel"
            )
            self.options_empty_label.grid(row=0, column=0, sticky="w")
            self._option_var.set("")
            return
        for index, option in enumerate(snapshot.options):
            option_label = translate_option_label(
                getattr(option, "label", "") or "", self.translator
            )
            radio = ttk.Radiobutton(
                self.options_inner,
                text=option_label or self.tr("not_found"),
                value=option.id,
                variable=self._option_var,
                style="Option.TRadiobutton",
            )
            radio.grid(row=index * 2, column=0, sticky="w")
            self._option_radio_by_id[option.id] = radio
            description = translate_option_description(
                getattr(option, "description", "") or "", self.translator
            )
            if description:
                label = ttk.Label(
                    self.options_inner,
                    text=description,
                    style="Hint.TLabel",
                    anchor="w",
                    justify="left",
                )
                label.grid(
                    row=index * 2 + 1,
                    column=0,
                    sticky="w",
                    padx=(px(27), 0),
                    pady=(0, px(2)),
                )
                label.bind(
                    "<Button-1>",
                    lambda _event, option_id=option.id: self._select_option_from_label(option_id),
                )

    def _select_option_from_label(self, option_id: str) -> None:
        """Select an accelerator when its description line is clicked."""
        radio = self._option_radio_by_id.get(option_id)
        if radio is None:
            return
        try:
            self._option_var.set(option_id)
            radio.focus_set()
            self._update_action_states()
        except tk.TclError:
            pass

    def _populate_pending(self, snapshot: DetectionSnapshot) -> None:
        self._pending_placeholder_item = None
        for item in self.pending_tree.get_children(""):
            self.pending_tree.delete(item)
        try:
            self.pending_count_label.configure(
                text=self.tr("pending_changed", count=len(snapshot.pending))
                if snapshot.pending
                else ""
            )
        except tk.TclError:
            pass
        if not snapshot.pending:
            self._pending_placeholder_item = self.pending_tree.insert(
                "",
                "end",
                values=(self.tr("pending_empty"), "", ""),
                tags=(PLACEHOLDER_ROW_TAG,),
            )
            self._sync_tree_scrollbar(self.pending_tree, self._pending_scroll)
            try:
                self._pending_card.grid_remove()
            except (tk.TclError, AttributeError):
                pass
            self._sync_body_height()
            self._queue_body_sync()
            return
        for change in snapshot.pending:
            pending_option = translate_option_label(
                getattr(change, "option_label", "") or "", self.translator
            )
            self.pending_tree.insert(
                "",
                "end",
                values=(
                    getattr(change, "browser_name", "") or self.tr("not_found"),
                    pending_option or self.tr("not_found"),
                    self._format_date(getattr(change, "applied_at", "")),
                ),
            )
        self._sync_tree_scrollbar(self.pending_tree, self._pending_scroll)
        try:
            if not self._pending_card.winfo_manager():
                self._pending_card.grid()
        except (tk.TclError, AttributeError):
            pass
        self._sync_body_height()
        self._queue_body_sync()

    def _sync_tree_scrollbar(self, tree: ttk.Treeview, scrollbar: ttk.Scrollbar) -> None:
        """Show the scrollbar only when there are more rows than the view fits."""
        try:
            rows = len(tree.get_children(""))
            visible = int(tree.cget("height"))
            if rows > visible:
                if not scrollbar.winfo_manager():
                    scrollbar.grid()
            elif scrollbar.winfo_manager():
                scrollbar.grid_remove()
        except (tk.TclError, ValueError):
            pass

    def _populate_notes(self, snapshot: DetectionSnapshot) -> None:
        """Backend notes are collected but not shown: the info bar was removed."""
        return

    def _populate_browsers(self, snapshot: DetectionSnapshot) -> None:
        previous_id = ""
        browser = self.current_browser()
        if browser is not None:
            previous_id = browser.id
        if not previous_id:
            previous_id = self._restore_browser_id
            self._restore_browser_id = ""
        values = [self._browser_display(b) for b in snapshot.browsers]
        self.browser_combo.configure(values=values)
        if not values:
            self.browser_combo.configure(state="disabled")
            self.browser_combo.set(self.tr("not_found"))
            self.browser_summary_label.configure(text=self.tr("no_browsers_summary"))
            return
        self.browser_combo.configure(state="readonly")
        index = 0
        if previous_id:
            for candidate_index, candidate in enumerate(snapshot.browsers):
                if candidate.id == previous_id:
                    index = candidate_index
                    break
        self.browser_combo.current(index)
        names = ", ".join(getattr(b, "name", "") for b in snapshot.browsers)
        self.browser_summary_label.configure(
            text=self.tr(
                "browsers_summary", count=len(snapshot.browsers), names=names
            )
        )

    def _browser_display(self, browser: Browser) -> str:
        name = getattr(browser, "name", "") or self.tr("not_found")
        engine = getattr(browser, "engine", "") or ""
        version = getattr(browser, "version", "") or ""
        details = " ".join(part for part in (engine, version) if part)
        return f"{name} ({details})" if details else name

    @staticmethod
    def _format_date(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return "—"
        try:
            moment = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        return moment.strftime("%d.%m.%Y %H:%M")

    # ------------------------------------------------------------------
    # Selection & action state
    # ------------------------------------------------------------------
    def current_browser(self) -> Optional[Browser]:
        snapshot = self._snapshot
        if snapshot is None or not snapshot.browsers:
            return None
        try:
            index = self.browser_combo.current()
        except tk.TclError:
            return None
        if index < 0 or index >= len(snapshot.browsers):
            return None
        return snapshot.browsers[index]

    def select_browser_index(self, index: int) -> None:
        snapshot = self._snapshot
        if snapshot is None or not snapshot.browsers:
            return
        index = max(0, min(index, len(snapshot.browsers) - 1))
        self.browser_combo.current(index)
        self._on_browser_selected()

    def select_browser_by_id(self, browser_id: str) -> bool:
        snapshot = self._snapshot
        if snapshot is None:
            return False
        for index, browser in enumerate(snapshot.browsers):
            if browser.id == browser_id:
                self.select_browser_index(index)
                return True
        return False

    def selected_option(self) -> Optional[GpuOption]:
        snapshot = self._snapshot
        if snapshot is None:
            return None
        option_id = self._option_var.get()
        for option in snapshot.options:
            if option.id == option_id:
                return option
        return None

    def select_option(self, option_id: str) -> bool:
        snapshot = self._snapshot
        if snapshot is None:
            return False
        if option_id not in self._option_radio_by_id:
            return False
        self._option_var.set(option_id)
        return True

    def _on_browser_selected(self, _event: "tk.Event[Any]" = None) -> None:
        snapshot = self._snapshot
        browser = self.current_browser()
        if snapshot is None or browser is None:
            self.current_label.configure(
                text=f"{self.tr('current_prefix')} {self.tr('not_found')}"
            )
            self._show_current_note(False)
            self._show_running_warning(False)
            self._show_restore_browser_button(False)
            self._update_action_states()
            return

        option = snapshot.current.get(browser.id)
        if option is None:
            self.current_label.configure(
                text=f"{self.tr('current_prefix')} {self.tr('not_found')}"
            )
        else:
            current_text = translate_option_label(
                getattr(option, "label", "") or "", self.translator
            )
            self.current_label.configure(
                text=f"{self.tr('current_prefix')} {current_text or self.tr('not_found')}"
            )
        self._show_current_note(bool(option is not None and option.kind == "auto"))
        if option is not None and option.id in self._option_radio_by_id:
            self._option_var.set(option.id)

        running = bool(snapshot.running.get(browser.id))
        self._show_running_warning(running)
        self._show_restore_browser_button(
            any(change.browser_id == browser.id for change in snapshot.pending)
        )
        self._update_action_states()

    def _show_current_note(self, visible: bool) -> None:
        # The explanatory line stays hidden by design; only the state is kept
        # (the smoke tests and the automation rely on the flag).
        self._current_note_shown = bool(visible)
        try:
            self.current_note_label.grid_remove()
        except tk.TclError:
            pass
        self._queue_body_sync()

    def _show_running_warning(self, visible: bool) -> None:
        self._running_warning_shown = bool(visible)
        if visible:
            self.running_frame.grid()
        else:
            self.running_frame.grid_remove()
        self._queue_body_sync()

    def _show_restore_browser_button(self, visible: bool) -> None:
        self._restore_browser_shown = bool(visible)
        if visible:
            self.restore_browser_button.grid()
        else:
            self.restore_browser_button.grid_remove()
        self._queue_body_sync()

    def _is_browser_running(self, browser_id: str) -> bool:
        if not self._snapshot or browser_id not in self._snapshot.running:
            return False
        return bool(self._snapshot.running[browser_id])

    def _update_action_states(self) -> None:
        browser = self.current_browser()
        running = self._is_browser_running(browser.id) if browser is not None else False
        has_options = bool(self._snapshot is not None and self._snapshot.options)
        can_apply = (
            not self._busy
            and not self._closing
            and browser is not None
            and not running
            and has_options
        )
        self._set_enabled(self.apply_button, can_apply)
        self._set_enabled(self.restore_all_button, not self._busy and not self._closing)
        self._set_enabled(self.check_again_button, not self._busy and not self._closing)
        self._set_enabled(
            self.restore_browser_button,
            not self._busy and not self._closing and self._restore_browser_shown,
        )
        try:
            if self._snapshot is not None and self._snapshot.browsers and not self._busy:
                self.browser_combo.configure(state="readonly")
            else:
                self.browser_combo.configure(state="disabled")
        except tk.TclError:
            pass
        self._update_action_hint(browser, running, has_options)

    def _update_action_hint(
        self, browser: Optional[Browser], running: bool, has_options: bool
    ) -> None:
        """Explain in one muted line why the primary button is unavailable."""
        hint = ""
        if not self._busy and not self._closing:
            if browser is None:
                hint = self.tr("hint_select_browser")
            elif running:
                hint = self.tr("hint_close_browser")
            elif not has_options:
                hint = self.tr("hint_no_options")
        label = getattr(self, "action_hint_label", None)
        if label is None:
            return
        try:
            label.configure(text=hint)
        except tk.TclError:
            pass

    @staticmethod
    def _set_enabled(widget: Optional[ttk.Widget], enabled: bool) -> None:
        if widget is None:
            return
        try:
            if enabled:
                widget.state(["!disabled"])
            else:
                widget.state(["disabled"])
        except tk.TclError:
            pass

    def _set_status(self, text: str, kind: str = INFO) -> None:
        try:
            self.status_var.set(text or "")
            self.status_label.configure(style=_STATUS_STYLES.get(kind, _STATUS_STYLES[INFO]))
            dot = getattr(self, "_status_dot", None)
            if dot is not None:
                dot.itemconfigure(self._status_dot_item, fill=self.theme.status_color(kind))
        except tk.TclError:
            pass

    def _set_running_state(self, browser: Browser, running: bool) -> None:
        if self._snapshot is not None:
            self._snapshot.running[browser.id] = bool(running)
        current = self.current_browser()
        if current is not None and current.id == browser.id:
            self._show_running_warning(bool(running))
        self._update_action_states()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def check_again(self) -> None:
        browser = self.current_browser()
        if browser is None or self._busy:
            return
        self._set_status(self.tr("status_checking"), INFO)
        try:
            running = bool(self.backend.is_browser_running(browser))
        except Exception as exc:
            self._set_status(f"{self.tr('status_checking')} {exc}", ERROR)
            return
        try:
            pids = list(self.backend.running_pids(browser) or [])
        except Exception:
            pids = []
        if self._snapshot is not None:
            self._snapshot.pids[browser.id] = pids
        self._set_running_state(browser, running)
        if running:
            self._set_status(self.tr("status_check_running"), ERROR)
        else:
            self._set_status(self.tr("status_check_stopped"), OK)

    def apply_selected(self) -> Optional[ApplyResult]:
        if self._busy or self._closing:
            return None
        browser = self.current_browser()
        if browser is None:
            message = self.tr("status_no_browser")
            self._set_status(message, ERROR)
            return ApplyResult.failure(message)
        option = self.selected_option()
        if option is None:
            message = self.tr("status_no_option")
            self._set_status(message, ERROR)
            return ApplyResult.failure(message)
        if self._is_browser_running(browser.id):
            running_message = self.tr("running_warning")
            self._set_status(running_message, ERROR)
            self._update_action_states()
            return ApplyResult.failure(running_message)

        try:
            result = self.backend.apply(browser, option)
        except Exception as exc:
            result = ApplyResult.failure(f"{self.tr('status_apply_failed')} {exc}")
        if not isinstance(result, ApplyResult):  # defensive: a broken backend
            result = ApplyResult.failure(self.tr("status_apply_failed"))

        if result.ok:
            self.refresh_now(result.message or self.tr("status_applied"), OK)
            self.show_ready_dialog(browser, option, result)
        else:
            message = result.message or STATUS_APPLY_FAILED
            if result.details and result.details not in message:
                message = f"{message} {result.details}"
            self.refresh_now(message, ERROR)
        return result

    def restore_all(self) -> Optional[ApplyResult]:
        if self._busy or self._closing:
            return None
        if not self.confirm(self.tr("restore_all_title"), self.tr("restore_all_confirm")):
            return None
        pending_before = list(self._snapshot.pending) if self._snapshot else []
        names = [change.browser_name for change in pending_before if change.browser_name]
        try:
            result = self.backend.restore_all()
        except Exception as exc:
            result = ApplyResult.failure(f"{self.tr('status_restore_failed')} {exc}")
        if not isinstance(result, ApplyResult):
            result = ApplyResult.failure(self.tr("status_restore_failed"))

        if result.ok:
            parts = [result.message or self.tr("status_restored")]
            if names:
                parts.append(self.tr("status_restored_names", names=", ".join(names)))
            else:
                parts.append(self.tr("status_restore_empty"))
            message = " ".join(part for part in parts if part)
            self.refresh_now(message, OK)
            self.notify(self.tr("restore_done_title"), message)
        else:
            message = result.message or self.tr("status_restore_failed")
            self.refresh_now(message, ERROR)
        return result

    def restore_selected_browser(self) -> Optional[ApplyResult]:
        if self._busy or self._closing:
            return None
        browser = self.current_browser()
        if browser is None:
            self._set_status(self.tr("status_no_browser"), ERROR)
            return None
        if not self.confirm(
            self.tr("restore_browser_title"),
            self.tr("restore_browser_confirm", browser=browser.name),
        ):
            return None
        has_pending = bool(
            self._snapshot
            and any(change.browser_id == browser.id for change in self._snapshot.pending)
        )
        message = self.tr("status_restore_browser", browser=browser.name)
        if not has_pending:
            no_changes = self.tr("status_no_changes", browser=browser.name)
            self._set_status(no_changes, INFO)
            return ApplyResult.success(no_changes)
        try:
            result = self.backend.restore_browser(browser)
        except Exception as exc:
            result = ApplyResult.failure(f"{self.tr('status_restore_failed')} {exc}")
        if not isinstance(result, ApplyResult):
            result = ApplyResult.failure(self.tr("status_restore_failed"))
        if result.ok:
            self.refresh_now(message, OK)
        else:
            self.refresh_now(result.message or self.tr("status_restore_failed"), ERROR)
        return result

    # ------------------------------------------------------------------
    # Ready dialog ("Все настроено, запустите браузер")
    # ------------------------------------------------------------------
    def show_ready_dialog(
        self, browser: Browser, option: GpuOption, result: Optional[ApplyResult] = None
    ) -> None:
        px = self.theme.px
        self.close_ready_dialog()
        dialog = tk.Toplevel(self.root)
        self._ready_dialog = dialog
        dialog.title(self.tr("ready_title"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        try:
            dialog.configure(background=self.theme.colors["card"])
        except tk.TclError:
            pass

        frame = ttk.Frame(
            dialog,
            style="Dialog.TFrame",
            padding=(px(24), px(22), px(24), px(20)),
        )
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        icon = tk.Canvas(
            frame,
            width=px(40),
            height=px(40),
            background=self.theme.colors["card"],
            highlightthickness=0,
            borderwidth=0,
        )
        icon.grid(row=0, column=0, sticky="nw", padx=(0, px(16)))
        self._draw_success_icon(icon)

        ttk.Label(
            frame,
            text=self.tr("ready_title"),
            style="DialogTitle.TLabel",
            anchor="w",
            justify="left",
            wraplength=px(380),
        ).grid(row=0, column=1, sticky="ew")
        ttk.Label(
            frame,
            text=self.tr(
                "ready_detail",
                browser=browser.name,
                option=translate_option_label(
                    getattr(option, "label", "") or "", self.translator
                ),
            ),
            style="DialogBody.TLabel",
            anchor="w",
            justify="left",
            wraplength=px(432),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(px(16), 0))
        ttk.Label(
            frame,
            text=self.tr("ready_hint"),
            style="DialogHint.TLabel",
            anchor="w",
            justify="left",
            wraplength=px(432),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(px(4), 0))

        warnings = list(getattr(result, "warnings", ()) or ()) if result is not None else []
        row = 3
        if warnings:
            banner = ttk.Frame(
                frame, style="RunningBanner.TFrame", padding=(px(12), px(8), px(12), px(8))
            )
            banner.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(px(12), 0))
            banner.columnconfigure(0, weight=1)
            ttk.Label(
                banner,
                text=self.tr("ready_warnings_prefix") + " " + "; ".join(warnings),
                style="Warning.TLabel",
                anchor="w",
                justify="left",
                wraplength=px(400),
            ).grid(row=0, column=0, sticky="ew")
            row += 1

        buttons = ttk.Frame(frame, style="Dialog.TFrame")
        buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(px(20), 0))
        buttons.columnconfigure(0, weight=1)
        ttk.Button(
            buttons,
            text=self.tr("close"),
            style="Secondary.TButton",
            command=self.close_ready_dialog,
        ).grid(row=0, column=1, padx=(0, px(8)))
        ttk.Button(
            buttons,
            text=self.tr("launch"),
            style="Accent.TButton",
            command=lambda: self._launch_browser(browser),
        ).grid(row=0, column=2)

        dialog.protocol("WM_DELETE_WINDOW", self.close_ready_dialog)
        dialog.bind("<Escape>", lambda _event: (self.close_ready_dialog(), "break")[1])
        self._center_dialog(dialog)
        try:
            self._grab_after_id = dialog.after_idle(self._grab_ready_dialog)
        except tk.TclError:
            self._grab_after_id = None

    def _draw_success_icon(self, canvas: "tk.Canvas") -> None:
        """Paint the Fluent-style success badge (a filled circle and a check)."""
        px = self.theme.px
        colors = self.theme.colors
        size = px(40)
        canvas.create_oval(0, 0, size, size, fill=colors["accent_soft"], outline="")
        canvas.create_line(
            px(11),
            px(20),
            px(17),
            px(26),
            px(29),
            px(14),
            fill=colors["accent"],
            width=max(2, px(2)),
            capstyle="round",
            joinstyle="round",
        )

    def _center_dialog(self, dialog: tk.Toplevel) -> None:
        try:
            dialog.update_idletasks()
            width = max(dialog.winfo_reqwidth(), self.theme.px(480))
            height = max(dialog.winfo_reqheight(), self.theme.px(228))
            root_width = self.root.winfo_width()
            root_height = self.root.winfo_height()
            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
            x = root_x + max((root_width - width) // 2, 0)
            y = root_y + max((root_height - height) // 3, 0)
            dialog.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass

    def _grab_ready_dialog(self) -> None:
        dialog = self._ready_dialog
        if dialog is None or not self._dialog_alive():
            return
        try:
            dialog.grab_set()
        except tk.TclError:
            pass

    def _dialog_alive(self) -> bool:
        dialog = self._ready_dialog
        if dialog is None:
            return False
        try:
            return bool(dialog.winfo_exists())
        except tk.TclError:
            return False

    def close_ready_dialog(self) -> None:
        dialog = self._ready_dialog
        self._ready_dialog = None
        after_id = self._grab_after_id
        self._grab_after_id = None
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        if dialog is None:
            return
        try:
            if dialog.winfo_exists():
                try:
                    dialog.grab_release()
                except tk.TclError:
                    pass
                dialog.destroy()
        except tk.TclError:
            pass

    def _launch_browser(self, browser: Browser) -> None:
        try:
            result = self.backend.launch(browser)
        except Exception as exc:
            message = f"{self.tr('status_launch_failed')} {exc}"
            self._set_status(message, ERROR)
            self.notify(self.tr("launch_dialog_title"), message)
            return
        if result is None:
            message = self.tr("status_launch_failed")
        elif result.ok:
            message = result.message or self.tr("status_launched", browser=browser.name)
        else:
            message = result.message or self.tr("status_launch_failed")
        self._set_status(message, OK if (result is not None and result.ok) else ERROR)
        self.notify(self.tr("launch_dialog_title"), message)

    # ------------------------------------------------------------------
    # Screenshot helper (dev only)
    # ------------------------------------------------------------------
    def _prepare_screenshot_view(self, snapshot: DetectionSnapshot) -> None:
        self._screenshot_prepared = True
        index = 0
        for candidate_index, browser in enumerate(snapshot.browsers):
            if "chrome" in (getattr(browser, "name", "") or "").lower():
                index = candidate_index
                break
        if snapshot.browsers:
            self.select_browser_index(index)

    # ------------------------------------------------------------------
    # Dialog hooks
    # ------------------------------------------------------------------
    def _ask_confirm(self, title: str, message: str) -> bool:
        try:
            return bool(messagebox.askyesno(title, message, parent=self.root))
        except tk.TclError:
            return False

    def _show_info(self, title: str, message: str) -> None:
        parent = self._ready_dialog if self._dialog_alive() else self.root
        try:
            messagebox.showinfo(title, message, parent=parent)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Public inspection helpers (used by smoke tests and automation)
    # ------------------------------------------------------------------
    @property
    def detection_finished(self) -> bool:
        return self._snapshot is not None and not self._busy

    @property
    def default_note_visible(self) -> bool:
        return self._current_note_shown

    @property
    def running_warning_visible(self) -> bool:
        return self._running_warning_shown

    @property
    def restore_browser_button_visible(self) -> bool:
        return self._restore_browser_shown

    @property
    def apply_enabled(self) -> bool:
        try:
            return not self.apply_button.instate(["disabled"])
        except tk.TclError:
            return False

    @property
    def status_text(self) -> str:
        try:
            return self.status_var.get()
        except tk.TclError:
            return ""

    def gpu_rows(self) -> List[Tuple[str, str, str]]:
        rows: List[Tuple[str, str, str]] = []
        try:
            for item in self.gpu_tree.get_children(""):
                rows.append(tuple(self.gpu_tree.item(item, "values")))
        except tk.TclError:
            pass
        return rows

    def pending_rows(self) -> List[Tuple[str, str, str]]:
        rows: List[Tuple[str, str, str]] = []
        try:
            for item in self.pending_tree.get_children(""):
                if item == self._pending_placeholder_item:
                    continue
                rows.append(tuple(self.pending_tree.item(item, "values")))
        except tk.TclError:
            pass
        return rows

    def pending_placeholder_visible(self) -> bool:
        try:
            return self._pending_placeholder_item is not None and bool(
                self.pending_tree.exists(self._pending_placeholder_item)
            )
        except tk.TclError:
            return False

    def option_labels(self) -> List[str]:
        labels: List[str] = []
        for child in self.options_inner.winfo_children():
            if isinstance(child, ttk.Radiobutton):
                labels.append(str(child.cget("text")))
        return labels

    def ready_dialog_open(self) -> bool:
        return self._dialog_alive()

    def ready_dialog_title(self) -> str:
        dialog = self._ready_dialog
        if dialog is None:
            return ""
        try:
            return str(dialog.title())
        except tk.TclError:
            return ""

    def ready_dialog_message(self) -> str:
        dialog = self._ready_dialog
        if dialog is None:
            return ""
        try:
            for child in dialog.winfo_children():
                for label in child.winfo_children():
                    try:
                        if label.cget("style") == "DialogTitle.TLabel":
                            return str(label.cget("text"))
                    except tk.TclError:
                        continue
        except tk.TclError:
            pass
        return ""

    # ------------------------------------------------------------------
    # Polling/cleanup
    # ------------------------------------------------------------------
    def _cancel_poll(self) -> None:
        poll_id = self._poll_id
        self._poll_id = None
        if poll_id is None:
            return
        try:
            self.root.after_cancel(poll_id)
        except tk.TclError:
            pass

    def shutdown(self) -> None:
        """Stop auxiliary activity and close the backend exactly once."""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._closing = True
        self._cancel_poll()
        if self._body_sync_id is not None:
            try:
                self.root.after_cancel(self._body_sync_id)
            except Exception:
                pass
            self._body_sync_id = None
        self.close_ready_dialog()
        try:
            self.backend.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def close(self) -> None:
        self.shutdown()
