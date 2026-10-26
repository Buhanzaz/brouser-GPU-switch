r"""BrouserGPUSwitch installer.

The installer is a small windowed program that carries the whole application
as bundled data (``payload/`` next to this script in the PyInstaller build).
It copies the payload into the per-user programs folder, creates shortcuts and
registers an uninstall entry - all without administrator rights.

Command line:
    BrouserGPUSwitch-Setup.exe                 interactive, asks nothing
    BrouserGPUSwitch-Setup.exe --silent        unattended install
    BrouserGPUSwitch-Setup.exe --silent --desktop  ... plus desktop shortcut
    BrouserGPUSwitch-Setup.exe --target DIR    install somewhere else
    BrouserGPUSwitch-Setup.exe --no-shortcuts --no-registry --no-launch

The application files themselves are copied from ``payload`` which the spec
file fills from ``dist/BrouserGPUSwitch``; when this script is run straight
from a source checkout the same folder is used directly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

APP_NAME = "BrouserGPUSwitch"
DISPLAY_NAME = "GPU Switch"
APP_VERSION = "1.0.0"
SM_FOLDER_NAME = "BrouserGPUSwitch"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BrouserGPUSwitch"

LANGUAGES = (("ru", "Русский"), ("en", "English"), ("zh", "中文"), ("es", "Español"), ("de", "Deutsch"))

TEXTS = {
    "ru": {
        "title": "Установка GPU Switch",
        "intro": "Программа будет установлена в папку:",
        "hint": "Права администратора не нужны. Язык интерфейса выбирается при первом запуске.",
        "language": "Язык установщика:",
        "launch": "Запустить программу после установки",
        "desktop": "Создать ярлык на рабочем столе",
        "install": "Установить",
        "close": "Закрыть",
        "cancel": "Отмена",
        "installing": "Установка…",
        "done": "Готово. Программа установлена.",
        "failed": "Не удалось установить: {error}",
        "exists": "Обновление уже установленной программы.",
    },
    "en": {
        "title": "Install GPU Switch",
        "intro": "The program will be installed to:",
        "hint": "Administrator rights are not required. The interface language is chosen on first launch.",
        "language": "Installer language:",
        "launch": "Launch the program after installation",
        "desktop": "Create a desktop shortcut",
        "install": "Install",
        "close": "Close",
        "cancel": "Cancel",
        "installing": "Installing…",
        "done": "Done. The program is installed.",
        "failed": "Installation failed: {error}",
        "exists": "Updating an existing installation.",
    },
    "zh": {
        "title": "安装 GPU Switch",
        "intro": "程序将安装到以下文件夹：",
        "hint": "无需管理员权限。界面语言在首次启动时选择。",
        "language": "安装程序语言：",
        "launch": "安装后启动程序",
        "desktop": "创建桌面快捷方式",
        "install": "安装",
        "close": "关闭",
        "cancel": "取消",
        "installing": "正在安装…",
        "done": "完成。程序已安装。",
        "failed": "安装失败：{error}",
        "exists": "正在更新已安装的程序。",
    },
    "es": {
        "title": "Instalar GPU Switch",
        "intro": "El programa se instalará en la carpeta:",
        "hint": "No se necesitan derechos de administrador. El idioma de la interfaz se elige en el primer inicio.",
        "language": "Idioma del instalador:",
        "launch": "Iniciar el programa después de instalar",
        "desktop": "Crear un acceso directo en el escritorio",
        "install": "Instalar",
        "close": "Cerrar",
        "cancel": "Cancelar",
        "installing": "Instalando…",
        "done": "Listo. El programa está instalado.",
        "failed": "No se pudo instalar: {error}",
        "exists": "Actualizando una instalación existente.",
    },
    "de": {
        "title": "GPU Switch installieren",
        "intro": "Das Programm wird in folgenden Ordner installiert:",
        "hint": "Administratorrechte sind nicht erforderlich. Die Sprache wird beim ersten Start gewählt.",
        "language": "Sprache des Installers:",
        "launch": "Programm nach der Installation starten",
        "desktop": "Verknüpfung auf dem Desktop erstellen",
        "install": "Installieren",
        "close": "Schließen",
        "cancel": "Abbrechen",
        "installing": "Installation läuft…",
        "done": "Fertig. Das Programm ist installiert.",
        "failed": "Installation fehlgeschlagen: {error}",
        "exists": "Eine vorhandene Installation wird aktualisiert.",
    },
}

CREATE_NO_WINDOW = 0x08000000


# ----------------------------------------------------------------------
# Environment helpers
# ----------------------------------------------------------------------
def data_dir() -> Path:
    """Per-user configuration folder, the same one the application uses."""
    override = os.environ.get("BROWSER_GPU_SWITCH_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "BrowserGpuSwitch"
    return Path.home() / ".config" / "browser-gpu-switch"


def detect_language() -> str:
    try:
        settings = json.loads((data_dir() / "settings.json").read_text(encoding="utf-8"))
        code = str(settings.get("language", "")).lower()
        if code in TEXTS:
            return code
    except Exception:
        pass
    try:
        import locale

        code = (locale.getlocale()[0] or "").lower()
    except Exception:
        code = ""
    for prefix, candidate in (("ru", "ru"), ("zh", "zh"), ("es", "es"), ("de", "de"), ("en", "en")):
        if code.startswith(prefix):
            return candidate
    return "en"


def default_target() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / "Programs" / APP_NAME


def payload_dir() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", "")
    if frozen_root:
        candidate = Path(frozen_root) / "payload"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent.parent / "dist" / APP_NAME


def parse_args(argv: list[str]) -> dict:
    options = {
        "silent": False,
        "desktop": False,
        "shortcuts": True,
        "registry": True,
        "launch": False,
        "target": default_target(),
    }
    for index, argument in enumerate(argv[1:]):
        if argument == "--silent":
            options["silent"] = True
        elif argument == "--desktop":
            options["desktop"] = True
        elif argument == "--no-shortcuts":
            options["shortcuts"] = False
        elif argument == "--no-registry":
            options["registry"] = False
        elif argument == "--launch":
            options["launch"] = True
        elif argument == "--target" and index + 2 < len(argv):
            options["target"] = Path(argv[index + 2]).expanduser()
        elif argument.startswith("--target="):
            options["target"] = Path(argument.split("=", 1)[1]).expanduser()
    return options


# ----------------------------------------------------------------------
# Installation steps
# ----------------------------------------------------------------------
def copy_payload(source: Path, target: Path, progress=None) -> int:
    target.mkdir(parents=True, exist_ok=True)
    files = [item for item in source.rglob("*") if item.is_file()]
    total = max(1, len(files))
    done = 0
    for item in files:
        relative = item.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)
        done += 1
        if progress is not None and done % 25 == 0:
            progress(done / total)
    if progress is not None:
        progress(1.0)
    return len(files)


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_powershell(script: str) -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            script,
        ],
        check=False,
        creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def create_shortcut(link: Path, target: Path, working_dir: Path) -> None:
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$s = $ws.CreateShortcut(%s); "
        "$s.TargetPath = %s; "
        "$s.WorkingDirectory = %s; "
        "$s.IconLocation = %s; "
        "$s.Save()"
    ) % (
        _ps_quote(str(link)),
        _ps_quote(str(target)),
        _ps_quote(str(working_dir)),
        _ps_quote(str(target) + ",0"),
    )
    run_powershell(script)


def uninstall_command(target: Path) -> str:
    start_menu = Path(os.environ.get("APPDATA") or Path.home()) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / SM_FOLDER_NAME
    desktop_link = Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop" / (APP_NAME + ".lnk")
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        "Remove-Item -LiteralPath %s -Recurse -Force; "
        "Remove-Item -LiteralPath %s -Recurse -Force; "
        "Remove-Item -LiteralPath %s -Force; "
        "Remove-Item -LiteralPath 'HKCU:\\%s' -Recurse -Force"
    ) % (_ps_quote(str(target)), _ps_quote(str(start_menu)), _ps_quote(str(desktop_link)), REGISTRY_KEY)
    return (
        "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command \"" + script + "\""
    )


def register_uninstall(target: Path) -> None:
    try:
        import winreg

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
        values = {
            "DisplayName": DISPLAY_NAME + " (" + APP_NAME + ")",
            "DisplayVersion": APP_VERSION,
            "Publisher": DISPLAY_NAME,
            "InstallLocation": str(target),
            "DisplayIcon": str(target / (APP_NAME + ".exe")),
            "UninstallString": uninstall_command(target),
            "NoModify": 1,
            "NoRepair": 1,
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ if isinstance(value, str) else winreg.REG_DWORD, value)
        winreg.CloseKey(key)
    except Exception:
        pass


def install_tree(target: Path, options: dict, progress=None) -> int:
    source = payload_dir()
    if not source.is_dir():
        raise RuntimeError("payload folder not found: %s" % source)
    count = copy_payload(source, target, progress)
    executable = target / (APP_NAME + ".exe")
    if options.get("shortcuts"):
        appdata = Path(os.environ.get("APPDATA") or Path.home())
        start_menu = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / SM_FOLDER_NAME
        create_shortcut(start_menu / (DISPLAY_NAME + ".lnk"), executable, target)
        create_shortcut(start_menu / ("Удалить " + DISPLAY_NAME + ".lnk"), Path("powershell.exe"), target)
        # The uninstall shortcut runs the same command that the registry stores.
        run_powershell(
            "$ws = New-Object -ComObject WScript.Shell; "
            "$s = $ws.CreateShortcut(%s); "
            "$s.TargetPath = 'powershell.exe'; "
            "$s.Arguments = %s; "
            "$s.WorkingDirectory = %s; "
            "$s.Save()"
            % (
                _ps_quote(str(start_menu / ("Удалить " + DISPLAY_NAME + ".lnk"))),
                _ps_quote(
                    "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "
                    + _ps_quote(
                        "Remove-Item -LiteralPath %s -Recurse -Force; Remove-Item -LiteralPath 'HKCU:\\%s' -Recurse -Force"
                        % (_ps_quote(str(target)), REGISTRY_KEY)
                    )
                ),
                _ps_quote(str(target)),
            )
        )
        if options.get("desktop"):
            desktop = Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop"
            create_shortcut(desktop / (APP_NAME + ".lnk"), executable, target)
    if options.get("registry"):
        register_uninstall(target)
    return count


def launch(target: Path) -> None:
    executable = target / (APP_NAME + ".exe")
    if not executable.is_file():
        return
    try:
        subprocess.Popen([str(executable)], cwd=str(target), creationflags=CREATE_NO_WINDOW)
    except OSError:
        pass


# ----------------------------------------------------------------------
# Interactive window
# ----------------------------------------------------------------------
class InstallerWindow:
    def __init__(self, root: tk.Tk, options: dict) -> None:
        self.root = root
        self.options = options
        self.language = detect_language()
        self.target = Path(options["target"])
        self.busy = False
        self.installed = False

        root.title(TEXTS[self.language]["title"])
        root.resizable(False, False)
        try:
            root.protocol("WM_DELETE_WINDOW", self.close)
        except tk.TclError:
            pass

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#F3F3F3")
        style.configure("TLabel", background="#F3F3F3", foreground="#1A1A1A")
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), background="#F3F3F3")
        style.configure("Muted.TLabel", foreground="#5C5C5C", background="#F3F3F3")
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

        frame = ttk.Frame(root, padding=(20, 16, 20, 14))
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)

        self.title_label = ttk.Label(frame, style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.intro_label = ttk.Label(frame, style="Muted.TLabel")
        self.intro_label.grid(row=1, column=0, sticky="w", pady=(10, 2))
        self.path_label = ttk.Label(frame, text=str(self.target), style="Muted.TLabel")
        self.path_label.grid(row=2, column=0, sticky="w")
        self.hint_label = ttk.Label(frame, style="Muted.TLabel", wraplength=460, justify="left")
        self.hint_label.grid(row=3, column=0, sticky="w", pady=(8, 0))

        self.language_frame = ttk.Frame(frame)
        self.language_frame.grid(row=4, column=0, sticky="w", pady=(12, 0))
        self.language_label = ttk.Label(self.language_frame, style="Muted.TLabel")
        self.language_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.language_combo = ttk.Combobox(
            self.language_frame,
            state="readonly",
            width=12,
            values=[name for _code, name in LANGUAGES],
        )
        self.language_combo.grid(row=0, column=1, sticky="w")
        self.language_combo.bind("<<ComboboxSelected>>", self.on_language)
        self.language_combo.set(dict(LANGUAGES)[self.language])

        self.launch_var = tk.BooleanVar(master=root, value=not options["silent"])
        self.desktop_var = tk.BooleanVar(master=root, value=bool(options["desktop"]))
        self.launch_box = ttk.Checkbutton(frame, variable=self.launch_var)
        self.launch_box.grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.desktop_box = ttk.Checkbutton(frame, variable=self.desktop_var)
        self.desktop_box.grid(row=6, column=0, sticky="w", pady=(2, 0))

        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100.0)
        self.progress.grid(row=7, column=0, sticky="ew", pady=(12, 4))
        self.status_label = ttk.Label(frame, style="Muted.TLabel")
        self.status_label.grid(row=8, column=0, sticky="w")

        buttons = ttk.Frame(frame)
        buttons.grid(row=9, column=0, sticky="e", pady=(12, 0))
        self.install_button = ttk.Button(buttons, style="Accent.TButton", command=self.start)
        self.install_button.grid(row=0, column=0, padx=(0, 8))
        self.close_button = ttk.Button(buttons, command=self.close)
        self.close_button.grid(row=0, column=1)

        self.apply_texts()
        self.center(520, 360)

    def center(self, width: int, height: int) -> None:
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 3)
            self.root.geometry("%dx%d+%d+%d" % (width, height, x, y))
        except tk.TclError:
            pass

    def text(self, key: str, **values) -> str:
        template = TEXTS[self.language][key]
        return template.format(**values) if values else template

    def apply_texts(self) -> None:
        self.root.title(self.text("title"))
        self.title_label.configure(text=self.text("title"))
        self.intro_label.configure(text=self.text("intro"))
        self.hint_label.configure(text=self.text("hint"))
        self.language_label.configure(text=self.text("language"))
        self.launch_box.configure(text=self.text("launch"))
        self.desktop_box.configure(text=self.text("desktop"))
        self.install_button.configure(text=self.text("install"))
        self.close_button.configure(text=(self.text("close") if self.installed else self.text("cancel")))

    def on_language(self, _event=None) -> None:
        name = str(self.language_combo.get())
        for code, label in LANGUAGES:
            if label == name:
                self.language = code
                break
        self.apply_texts()

    def start(self) -> None:
        if self.busy or self.installed:
            return
        self.busy = True
        self.install_button.configure(state="disabled")
        self.close_button.configure(state="disabled")
        self.status_label.configure(text=self.text("installing"))
        self.options["desktop"] = bool(self.desktop_var.get())
        self.root.update_idletasks()

        def progress(fraction: float) -> None:
            try:
                self.progress.configure(value=max(0.0, min(1.0, fraction)) * 100.0)
                self.root.update_idletasks()
            except tk.TclError:
                pass

        try:
            if self.target.exists() and any(self.target.iterdir()):
                self.status_label.configure(text=self.text("exists"))
                self.root.update_idletasks()
            install_tree(self.target, self.options, progress)
        except Exception as exc:
            self.status_label.configure(text=self.text("failed", error=exc))
            self.busy = False
            self.install_button.configure(state="normal")
            self.close_button.configure(state="normal")
            return

        self.installed = True
        self.busy = False
        self.status_label.configure(text=self.text("done"))
        self.close_button.configure(state="normal", text=self.text("close"))
        should_launch = bool(self.launch_var.get())
        if should_launch:
            launch(self.target)
        self.close()

    def close(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def log_line(message: str) -> None:
    """Print when a console exists; a windowed PyInstaller build has no stdout."""
    stream = sys.stdout
    if stream is None:
        return
    try:
        print(message, file=stream)
        stream.flush()
    except Exception:
        pass


def log_error(message: str) -> None:
    stream = sys.stderr
    if stream is None:
        return
    try:
        print(message, file=stream)
        stream.flush()
    except Exception:
        pass


def crash_log(text: str) -> None:
    """Keep the reason for an unexpected failure next to the settings file."""
    try:
        target = data_dir()
        target.mkdir(parents=True, exist_ok=True)
        (target / "setup-error.log").write_text(text, encoding="utf-8")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    options = parse_args(arguments)
    if options["silent"]:
        try:
            count = install_tree(Path(options["target"]), options)
        except Exception as exc:
            crash_log("silent install failed: %r" % (exc,))
            log_error("install failed: %s" % exc)
            return 1
        if options.get("launch"):
            launch(Path(options["target"]))
        log_line("installed %d files to %s" % (count, options["target"]))
        return 0
    try:
        root = tk.Tk()
    except Exception as exc:
        crash_log("cannot open the installer window: %r" % (exc,))
        log_error("cannot open the installer window: %s" % exc)
        return 2
    InstallerWindow(root, options)
    root.mainloop()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        import traceback

        crash_log(traceback.format_exc())
        raise
