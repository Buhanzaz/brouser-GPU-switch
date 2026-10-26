"""Windows 11 (Fluent) design tokens and ttk styles for the GPU Switch window.

Only the standard library is used: everything is expressed through
``ttk.Style`` on the built-in ``clam`` theme (the one theme that honours
colours on Windows, Linux and macOS alike), plus two tiny ``tk.Canvas``
strips where ttk cannot paint at all (the accent rule and the status dot).

The tokens follow the Windows 11 shell: a light page (``#F3F3F3``), white
cards with a 1 px hairline, Segoe UI Variable typography, an 8 px spacing
grid and the system accent blue ``#0067C0`` for the primary action.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

#: Windows 11 light palette.  Contrast ratios are noted where they matter.
LIGHT: Dict[str, str] = {
    "page": "#F3F3F3",
    "card": "#FFFFFF",
    "subtle": "#FBFBFB",
    "selected": "#EAF4FD",
    "stroke_card": "#E5E5E5",
    "stroke_control": "#D9D9D9",
    "divider": "#E0E0E0",
    "text": "#1A1A1A",
    "text2": "#5C5C5C",
    "text3": "#6E6E6E",
    "disabled": "#A6A6A6",
    "accent": "#0067C0",
    "accent_hover": "#1A76C4",
    "accent_pressed": "#005BA1",
    "accent_disabled": "#E8E8E8",
    "accent_soft": "#E8F3FC",
    "focus": "#004E92",
    "success": "#0F7B0F",
    "danger": "#C42B1C",
    "danger_stroke": "#EBBBB6",
    "danger_hover": "#FDF3F3",
    "danger_pressed": "#FBE7E5",
    "warn_surface": "#FDF3F3",
    "warn_stroke": "#F1C6C2",
    "info_surface": "#F0F6FC",
    "info_stroke": "#C7E0F4",
    "control_hover": "#F5F5F5",
    "control_pressed": "#EDEDED",
    "control_stroke_hover": "#C7C7C7",
    "row_alt": "#FAFAFA",
    "scroll_thumb": "#C9C9C9",
    "scroll_thumb_hover": "#A6A6A6",
    "indicator_border": "#8A8A8A",
}

#: Font families, best first.  "Segoe UI Variable Text" is the real family
#: name used by Windows 11; plain "Segoe UI" covers Windows 10.
FONT_FAMILIES = (
    "Segoe UI Variable Text",
    "Segoe UI",
    "Inter",
    "Noto Sans",
    "DejaVu Sans",
    "Liberation Sans",
    "Cantarell",
    "Ubuntu",
    "Arial",
)

#: Typographic scale, in device-independent pixels (multiplied by the DPI
#: factor inside :meth:`Theme.px`).
TITLE_SIZE = 20
SUBTITLE_SIZE = 14
CARD_TITLE_SIZE = 14
BODY_SIZE = 14
SMALL_SIZE = 12
TABLE_HEADING_SIZE = 12
BUTTON_SIZE = 14
DIALOG_TITLE_SIZE = 20
STATUS_SIZE = 12


class Theme:
    """ttk styles, palette and helpers for one Tk root window."""

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.colors = dict(LIGHT)
        self.style = ttk.Style(root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.family = self._pick_font_family()
        self.scale = self._dpi_scale()
        self._configure_defaults()
        self._configure_labels()
        self._configure_buttons()
        self._configure_inputs()
        self._configure_tables()
        self._configure_surfaces()
        self._configure_popdowns()

    # -- geometry helpers ---------------------------------------------------
    def px(self, value: float) -> int:
        """Convert a design pixel to a device pixel for this screen."""
        return max(1, int(round(float(value) * self.scale)))

    def pad(self, x: float, y: float) -> Tuple[int, int]:
        """Convert a padding pair to device pixels."""
        return (self.px(x), self.px(y))

    def font(self, size: int, weight: str = "") -> Tuple[Any, ...]:
        """Return a Tk font spec in device pixels (negative size = pixels)."""
        pixels = self.px(size)
        if weight:
            return (self.family, -pixels, weight)
        return (self.family, -pixels)

    def status_color(self, kind: str) -> str:
        return {
            "info": self.colors["text3"],
            "ok": self.colors["success"],
            "error": self.colors["danger"],
        }.get(kind, self.colors["text3"])

    # -- internals ----------------------------------------------------------
    def _dpi_scale(self) -> float:
        try:
            dpi = float(self.root.winfo_fpixels("1i"))
        except (tk.TclError, ValueError):
            dpi = 96.0
        return max(1.0, min(2.5, dpi / 96.0))

    def _pick_font_family(self) -> str:
        try:
            families = set(tkfont.families(self.root))
        except tk.TclError:
            families = set()
        for candidate in FONT_FAMILIES:
            if candidate in families:
                return candidate
        try:
            return tkfont.nametofont("TkDefaultFont").actual("family")
        except Exception:  # pragma: no cover - broken Tk install
            return "TkDefaultFont"

    # -- styles -------------------------------------------------------------
    def _configure_defaults(self) -> None:
        c = self.colors
        self.style.configure(".", background=c["page"], foreground=c["text"])
        self.style.configure("TFrame", background=c["page"])
        self.style.configure("TLabel", background=c["page"], foreground=c["text"], font=self.font(BODY_SIZE))
        self.style.configure(
            "TSeparator",
            background=c["divider"],
            bordercolor=c["divider"],
            lightcolor=c["divider"],
            darkcolor=c["divider"],
        )

    def _configure_labels(self) -> None:
        c = self.colors
        self.style.configure(
            "Title.TLabel", background=c["page"], foreground=c["text"], font=self.font(TITLE_SIZE, "bold")
        )
        self.style.configure(
            "Subtitle.TLabel",
            background=c["page"],
            foreground=c["text2"],
            font=self.font(SUBTITLE_SIZE),
        )
        self.style.configure(
            "Version.TLabel", background=c["page"], foreground=c["text3"], font=self.font(SMALL_SIZE)
        )
        self.style.configure(
            "CardTitle.TLabel",
            background=c["card"],
            foreground=c["text"],
            font=self.font(CARD_TITLE_SIZE, "bold"),
        )
        self.style.configure(
            "CardHint.TLabel",
            background=c["card"],
            foreground=c["text3"],
            font=self.font(SMALL_SIZE),
        )
        self.style.configure(
            "Prompt.TLabel",
            background=c["card"],
            foreground=c["text2"],
            font=self.font(SMALL_SIZE),
        )
        self.style.configure(
            "Body.TLabel", background=c["card"], foreground=c["text"], font=self.font(BODY_SIZE)
        )
        self.style.configure(
            "SystemLabel.TLabel",
            background=c["subtle"],
            foreground=c["text"],
            font=self.font(BODY_SIZE),
        )
        self.style.configure(
            "SystemCaption.TLabel",
            background=c["subtle"],
            foreground=c["text2"],
            font=self.font(SMALL_SIZE, "bold"),
        )
        self.style.configure(
            "Current.TLabel",
            background=c["subtle"],
            foreground=c["text"],
            font=self.font(BODY_SIZE, "bold"),
        )
        self.style.configure(
            "Hint.TLabel", background=c["card"], foreground=c["text3"], font=self.font(SMALL_SIZE)
        )
        self.style.configure(
            "HintOnPage.TLabel",
            background=c["page"],
            foreground=c["text3"],
            font=self.font(SMALL_SIZE),
        )
        self.style.configure(
            "Warning.TLabel",
            background=c["warn_surface"],
            foreground=c["danger"],
            font=self.font(SMALL_SIZE),
        )
        self.style.configure(
            "InfoBar.TLabel",
            background=c["info_surface"],
            foreground=c["text2"],
            font=self.font(SMALL_SIZE),
        )
        self.style.configure(
            "ActionHint.TLabel",
            background=c["card"],
            foreground=c["text3"],
            font=self.font(SMALL_SIZE),
        )
        for name, colour in (
            ("Status.TLabel", c["text2"]),
            ("StatusOk.TLabel", c["success"]),
            ("StatusError.TLabel", c["danger"]),
        ):
            self.style.configure(
                name, background=c["subtle"], foreground=colour, font=self.font(STATUS_SIZE)
            )
        self.style.configure(
            "StatusHint.TLabel",
            background=c["subtle"],
            foreground=c["text3"],
            font=self.font(STATUS_SIZE),
        )
        self.style.configure(
            "DialogTitle.TLabel",
            background=c["card"],
            foreground=c["text"],
            font=self.font(DIALOG_TITLE_SIZE, "bold"),
        )
        self.style.configure(
            "DialogBody.TLabel", background=c["card"], foreground=c["text"], font=self.font(BODY_SIZE)
        )
        self.style.configure(
            "DialogHint.TLabel",
            background=c["card"],
            foreground=c["text2"],
            font=self.font(SMALL_SIZE),
        )

    def _configure_buttons(self) -> None:
        c = self.colors
        common = dict(
            relief="flat",
            borderwidth=1,
            focusthickness=1,
            padding=self.pad(16, 4),
            font=self.font(BUTTON_SIZE, "bold"),
            width=0,
            anchor="center",
        )
        # Every plain TButton is a secondary button, so nothing looks native.
        self.style.configure(
            "TButton",
            background=c["card"],
            foreground=c["text"],
            bordercolor=c["stroke_control"],
            lightcolor=c["card"],
            darkcolor=c["card"],
            focuscolor=c["focus"],
            **common,
        )
        self.style.configure(
            "Secondary.TButton",
            background=c["card"],
            foreground=c["text"],
            bordercolor=c["stroke_control"],
            lightcolor=c["card"],
            darkcolor=c["card"],
            focuscolor=c["focus"],
            **common,
        )
        self.style.map(
            "Secondary.TButton",
            background=[
                ("disabled", c["card"]),
                ("pressed", c["control_pressed"]),
                ("active", c["control_hover"]),
            ],
            foreground=[("disabled", c["disabled"]), ("!disabled", c["text"])],
            bordercolor=[
                ("disabled", c["stroke_card"]),
                ("focus", c["focus"]),
                ("active", c["control_stroke_hover"]),
                ("!disabled", c["stroke_control"]),
            ],
            lightcolor=[("active", c["control_hover"])],
            darkcolor=[("active", c["control_hover"])],
        )
        self.style.configure(
            "Accent.TButton",
            background=c["accent"],
            foreground="#FFFFFF",
            bordercolor=c["accent"],
            lightcolor=c["accent"],
            darkcolor=c["accent"],
            focuscolor="#FFFFFF",
            **common,
        )
        self.style.map(
            "Accent.TButton",
            background=[
                ("disabled", c["accent_disabled"]),
                ("pressed", c["accent_pressed"]),
                ("active", c["accent_hover"]),
            ],
            foreground=[("disabled", c["disabled"]), ("!disabled", "#FFFFFF")],
            bordercolor=[
                ("disabled", c["accent_disabled"]),
                ("focus", c["focus"]),
                ("pressed", c["accent_pressed"]),
                ("active", c["accent_hover"]),
                ("!disabled", c["accent"]),
            ],
            lightcolor=[
                ("disabled", c["accent_disabled"]),
                ("pressed", c["accent_pressed"]),
                ("active", c["accent_hover"]),
            ],
            darkcolor=[
                ("disabled", c["accent_disabled"]),
                ("pressed", c["accent_pressed"]),
                ("active", c["accent_hover"]),
            ],
        )
        self.style.configure(
            "Danger.TButton",
            background=c["card"],
            foreground=c["danger"],
            bordercolor=c["danger_stroke"],
            lightcolor=c["card"],
            darkcolor=c["card"],
            focuscolor=c["danger"],
            **common,
        )
        self.style.map(
            "Danger.TButton",
            background=[
                ("disabled", c["card"]),
                ("pressed", c["danger_pressed"]),
                ("active", c["danger_hover"]),
            ],
            foreground=[("disabled", "#D8A7A2"), ("!disabled", c["danger"])],
            bordercolor=[
                ("disabled", c["stroke_card"]),
                ("focus", c["danger"]),
                ("active", "#E8B3AD"),
                ("!disabled", c["danger_stroke"]),
            ],
            lightcolor=[("active", c["danger_hover"])],
            darkcolor=[("active", c["danger_hover"])],
        )
        self.style.configure(
            "Small.Secondary.TButton",
            background=c["card"],
            foreground=c["text"],
            bordercolor=c["stroke_control"],
            lightcolor=c["card"],
            darkcolor=c["card"],
            focuscolor=c["focus"],
            relief="flat",
            borderwidth=1,
            focusthickness=1,
            padding=self.pad(12, 5),
            font=self.font(SMALL_SIZE),
        )
        self.style.map(
            "Small.Secondary.TButton",
            background=[
                ("disabled", c["card"]),
                ("pressed", c["control_pressed"]),
                ("active", c["control_hover"]),
            ],
            foreground=[("disabled", c["disabled"]), ("!disabled", c["text"])],
            bordercolor=[
                ("disabled", c["stroke_card"]),
                ("focus", c["focus"]),
                ("active", c["control_stroke_hover"]),
                ("!disabled", c["stroke_control"]),
            ],
            lightcolor=[("active", c["control_hover"])],
            darkcolor=[("active", c["control_hover"])],
        )

    def _configure_inputs(self) -> None:
        c = self.colors
        self.style.configure(
            "Browser.TCombobox",
            fieldbackground=c["card"],
            background=c["card"],
            foreground=c["text"],
            arrowcolor=c["text2"],
            bordercolor=c["stroke_control"],
            lightcolor=c["card"],
            darkcolor=c["card"],
            padding=self.pad(10, 5),
            relief="flat",
            font=self.font(BODY_SIZE),
            selectbackground=c["accent"],
            selectforeground="#FFFFFF",
        )
        self.style.map(
            "Browser.TCombobox",
            fieldbackground=[("readonly", c["card"]), ("disabled", c["page"])],
            background=[("readonly", c["card"]), ("disabled", c["page"])],
            foreground=[("disabled", c["disabled"])],
            arrowcolor=[("disabled", c["disabled"])],
            bordercolor=[("focus", c["accent"]), ("active", c["stroke_control"])],
            lightcolor=[("focus", c["accent"])],
            darkcolor=[("focus", c["accent"])],
        )
        self.style.configure(
            "Option.TRadiobutton",
            background=c["card"],
            foreground=c["text"],
            font=self.font(BODY_SIZE),
            indicatorsize=self.px(13),
            indicatormargin=self.pad(8, 0),
            indicatorbackground=c["card"],
            indicatorforeground=c["accent"],
            upperbordercolor=c["indicator_border"],
            lowerbordercolor=c["indicator_border"],
            focuscolor=c["accent"],
            focusthickness=1,
            padding=self.pad(2, 2),
        )
        self.style.map(
            "Option.TRadiobutton",
            background=[("disabled", c["card"]), ("pressed", c["control_pressed"]), ("active", c["control_hover"])],
            foreground=[("disabled", c["disabled"]), ("!disabled", c["text"])],
            indicatorforeground=[("disabled", c["disabled"]), ("selected", c["accent"]), ("!selected", c["card"])],
            indicatorbackground=[("disabled", c["card"]), ("!disabled", c["card"])],
            upperbordercolor=[("focus", c["accent"]), ("!disabled", c["indicator_border"])],
            lowerbordercolor=[("focus", c["accent"]), ("!disabled", c["indicator_border"])],
            lightcolor=[("active", c["control_hover"])],
            darkcolor=[("active", c["control_hover"])],
        )

    def _configure_tables(self) -> None:
        c = self.colors
        self.style.configure(
            "Fluent.Treeview",
            background=c["card"],
            fieldbackground=c["card"],
            foreground=c["text"],
            bordercolor=c["stroke_card"],
            lightcolor=c["card"],
            darkcolor=c["card"],
            borderwidth=0,
            relief="flat",
            rowheight=self.px(32),
            font=self.font(BODY_SIZE),
        )
        self.style.map(
            "Fluent.Treeview",
            background=[("selected", c["selected"])],
            foreground=[("selected", c["text"])],
        )
        self.style.configure(
            "Fluent.Treeview.Heading",
            background=c["subtle"],
            foreground=c["text2"],
            bordercolor=c["stroke_card"],
            lightcolor=c["subtle"],
            darkcolor=c["subtle"],
            relief="flat",
            borderwidth=0,
            padding=self.pad(5, 5),
            font=self.font(TABLE_HEADING_SIZE, "bold"),
        )
        self.style.map(
            "Fluent.Treeview.Heading",
            background=[("active", c["subtle"])],
            foreground=[("active", c["text"])],
        )

    def _configure_surfaces(self) -> None:
        c = self.colors
        self.style.configure("Page.TFrame", background=c["page"])
        self.style.configure("Card.TFrame", background=c["card"], bordercolor=c["stroke_card"], borderwidth=1, relief="solid")
        self.style.configure("CardBody.TFrame", background=c["card"])
        self.style.configure("Strip.TFrame", background=c["subtle"], bordercolor=c["stroke_card"], borderwidth=1, relief="solid")
        self.style.configure("Current.TFrame", background=c["subtle"], bordercolor=c["stroke_card"], borderwidth=1, relief="solid")
        self.style.configure("RunningBanner.TFrame", background=c["warn_surface"], bordercolor=c["warn_stroke"], borderwidth=1, relief="solid")
        self.style.configure("InfoBar.TFrame", background=c["info_surface"], bordercolor=c["info_stroke"], borderwidth=1, relief="solid")
        self.style.configure("ActionBar.TFrame", background=c["card"])
        self.style.configure("StatusBar.TFrame", background=c["subtle"])
        self.style.configure("Dialog.TFrame", background=c["card"])

    def _configure_popdowns(self) -> None:
        c = self.colors
        try:
            self.root.option_add("*TCombobox*Listbox*Background", c["card"])
            self.root.option_add("*TCombobox*Listbox*Foreground", c["text"])
            self.root.option_add("*TCombobox*Listbox*selectBackground", c["accent"])
            self.root.option_add("*TCombobox*Listbox*selectForeground", "#FFFFFF")
            self.root.option_add("*TCombobox*Listbox*Font", self._font_string(SMALL_SIZE))
        except tk.TclError:  # pragma: no cover - exotic Tk builds
            pass

    def _font_string(self, size: int) -> str:
        """Tk font string for option_add (listbox font is a string option)."""
        family = self.family if " " not in self.family else "{" + self.family + "}"
        return "{0} -{1}".format(family, self.px(size))

    # -- shared widget helpers ---------------------------------------------
    def card(self, parent: tk.Misc, **kwargs: Any) -> ttk.Frame:
        """Create a Windows 11 card: white surface, 1 px hairline, 16 px padding."""
        options: Dict[str, Any] = {"style": "Card.TFrame", "padding": (self.px(16), self.px(8))}
        options.update(kwargs)
        return ttk.Frame(parent, **options)

    def section_title(self, parent: tk.Misc, text: str) -> ttk.Label:
        return ttk.Label(parent, text=text, style="CardTitle.TLabel", anchor="w")


class ThinScrollbar(tk.Canvas):
    """A thin Fluent-style scrollbar: no arrow buttons, one rounded thumb.

    ``ttk.Scrollbar`` cannot drop its arrow buttons or become narrower than
    its theme's arrow size, so the page and the tables use this small canvas
    instead.  It speaks the usual scrollbar protocol: the owner passes
    ``command`` (``yview``) and calls :meth:`set` from ``yscrollcommand``.
    """

    def __init__(
        self,
        master: tk.Misc,
        command: Optional[Any] = None,
        *,
        width: int = 12,
        background: str = "#F3F3F3",
        thumb: str = "#C9C9C9",
        thumb_active: str = "#A6A6A6",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            width=width,
            highlightthickness=0,
            borderwidth=0,
            background=background,
            **kwargs,
        )
        self._command = command
        self._thumb_color = thumb
        self._thumb_active = thumb_active
        self._hover = False
        self._pressed = False
        self._first = 0.0
        self._last = 1.0
        self._drag_offset = 0.0
        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    # -- scrollbar protocol -------------------------------------------------
    def set(self, first: Any, last: Any) -> None:
        try:
            self._first = float(first)
            self._last = float(last)
        except (TypeError, ValueError):
            return
        self._redraw()

    # -- drawing ------------------------------------------------------------
    def _track_height(self) -> int:
        return max(self.winfo_height(), 1)

    def _thumb_box(self) -> Tuple[int, int]:
        height = self._track_height()
        first = min(max(self._first, 0.0), 1.0)
        last = min(max(self._last, 0.0), 1.0)
        top = int(round(first * height))
        bottom = int(round(last * height))
        minimum = min(24, height)
        if bottom - top < minimum:
            bottom = min(height, top + minimum)
            top = max(0, bottom - minimum)
        return top, bottom

    def _redraw(self) -> None:
        self.delete("thumb")
        if self._last - self._first >= 0.999:
            return
        top, bottom = self._thumb_box()
        colour = self._thumb_active if (self._hover or self._pressed) else self._thumb_color
        width = max(self.winfo_width(), 1)
        centre = width // 2
        thickness = max(4, min(width - 4, 6))
        self.create_line(
            centre,
            top + 5,
            centre,
            max(top + 6, bottom - 5),
            fill=colour,
            width=thickness,
            capstyle="round",
            tags="thumb",
        )

    # -- events -------------------------------------------------------------
    def _on_configure(self, _event: "tk.Event[Any]") -> None:
        self._redraw()

    def _on_enter(self, _event: "tk.Event[Any]") -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _event: "tk.Event[Any]") -> None:
        self._hover = False
        self._redraw()

    def _on_press(self, event: "tk.Event[Any]") -> None:
        top, bottom = self._thumb_box()
        if top <= int(event.y) <= bottom:
            self._pressed = True
            self._drag_offset = int(event.y) - top
            self._redraw()
            return
        self._scroll_to(max(0.0, min(1.0, int(event.y) / self._track_height())))

    def _on_drag(self, event: "tk.Event[Any]") -> None:
        if not self._pressed:
            return
        span = max(self._last - self._first, 1e-6)
        top = (int(event.y) - self._drag_offset) / self._track_height()
        self._scroll_to(max(0.0, min(1.0 - span, top)))

    def _on_release(self, _event: "tk.Event[Any]") -> None:
        self._pressed = False
        self._redraw()

    def _scroll_to(self, fraction: float) -> None:
        if self._command is None:
            return
        try:
            self._command("moveto", fraction)
        except Exception:  # pragma: no cover - the owner may be closing
            pass


def apply(root: tk.Misc) -> Theme:
    """Install the Fluent theme on *root* and return it."""
    return Theme(root)
