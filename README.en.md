# GPU Switch

**Language:** [Русский](README.md) · [English](README.en.md) · [中文](README.zh.md) · [Español](README.es.md) · [Deutsch](README.de.md)

A small desktop app for Windows and Linux that switches the graphics accelerator (GPU) used by a browser of your choice. Everything runs under the current user — no administrator rights needed. The interface follows the Windows 11 style: cards with a hairline border, Segoe UI Variable, the system accent color.

```
Windows 10/11 · Linux · Python 3.9+ · Tkinter · без сторонних библиотек
Установщик BrouserGPUSwitch-Setup.exe, один файл BrouserGPUSwitch.exe
и архив для Linux собираются build_exe.bat / build_linux.sh
```

## Why it's useful

On laptops and PCs with two graphics cards (integrated Intel/AMD and discrete NVIDIA/AMD), the browser may run on the weaker integrated graphics by default. GPU Switch lets you force Chrome, Edge, Firefox, Yandex Browser and other browsers to use the discrete GPU — and just as easily switch things back.

## What it does

1. Detects the operating system (Windows 10/11 or Linux), its version and architecture.
2. Finds installed browsers (the StartMenuInternet registry key and known paths on Windows; `.desktop` files on Linux).
3. Detects the graphics chips: integrated, discrete and virtual.
4. Shows a window to choose from: "Select a browser detected on your PC".
5. Preselects, in the accelerator list, the option currently in effect for the browser: it is marked as selected.
6. Lets you choose which accelerator to switch to.
7. Asks you to close the browser and verifies that it is really closed (by process).
8. Changes the settings on the system — for the current user only.
9. After the switch it shows an "All set, launch your browser" window with a button to launch that browser.
10. The always-available "Restore everything" button undoes every change the app has made.

## What it looks like

![GPU Switch main window](docs/gui-main.png)

*Main window: the "System", "Graphics cards" and "Browser" cards, the accelerator picker, and the accent "Apply" button pinned to the bottom.*

![Window after applying the setting](docs/gui-success.png)

*After the switch: "All set, launch your browser" with a button to launch the browser.*

## Languages

The interface is available in five languages: **Russian**, **English**, **Chinese**, **Spanish**, **German**.

The language is picked from the list in the top-right corner of the main window, next to the version number. On first launch the system language is used (or the one saved earlier). As soon as you pick a language the window restarts in it right away, and the choice is remembered in `settings.json` next to the app's data (see "Where data is stored") and reused on subsequent launches.

Only the app's interface elements are translated. Graphics card and browser names, and version numbers, are system data and are left as they are. The command-line service modes (`--self-test`, `--diagnostics`) always print their report in Russian.

## Requirements

* Windows 10 (1803 or later) or Windows 11, or Linux with X11/Wayland.
* Python 3.9+ with Tkinter.
  * Windows: [python.org](https://www.python.org/downloads/) — Tkinter comes with the installer.
  * Debian/Ubuntu: `sudo apt install python3-tk`
  * Fedora: `sudo dnf install python3-tkinter`
  * Arch: `sudo pacman -S tk`
* No third-party Python packages are required.
* The ready-made `BrouserGPUSwitch.exe` needs neither Python nor Tkinter — see "Ready-made installer and builds".

## Running

Windows:

```bat
run.bat
```

or from the command line:

```bat
py -3 main.py
```

Linux:

```sh
chmod +x run.sh
./run.sh
```

or:

```sh
python3 main.py
```

Demo mode (changes nothing on your computer, shows sample data):

```
python main.py --mock
```

## Ready-made installer and builds (no Python needed)

Build it yourself (an internet connection is needed once, to install PyInstaller):

```bat
build_exe.bat
```

The script checks for Python 3.9+, installs PyInstaller if necessary, and builds three variants:

* `dist\BrouserGPUSwitch-Setup.exe` — the installer. It offers an install folder, installs the app into `%LOCALAPPDATA%\Programs\BrouserGPUSwitch` (no administrator rights needed), creates Start menu shortcuts and optionally desktop ones, and adds "Uninstall GPU Switch" plus an entry in the Windows list of installed programs;
* `dist\BrouserGPUSwitch.exe` — a single file, around 11–12 MB, copied and moved around like any other exe;
* `dist\BrouserGPUSwitch\BrouserGPUSwitch.exe` — a folder with the support files next to it: nothing has to be extracted, so it starts even where the one-file build is blocked.

The installer carries the `dist\BrouserGPUSwitch` folder inside itself, so it has to be built after it — `build_exe.bat` takes care of that. Every variant runs a self-check at the end of the build, and the installer also does a trial silent install.

For Linux the project ships `build_linux.sh`: it builds `dist/BrouserGPUSwitch-linux-x86_64.tar.gz` — an archive with the program folder, `install.sh`, `uninstall.sh` and a `.desktop` shortcut. The user unpacks the archive and runs `./install.sh`; the app is installed into `~/.local` and root is not needed:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

If the project lives on GitHub, all of this is built automatically: **Actions** tab → **build** → **Run workflow**. The finished installer, one-file build, folder archive and Linux archive appear in the run's artifacts. Push a tag like `v1.0.0` and they're attached to the release — that way you can hand them to users with a link.

How the built file behaves:

* double-clicking opens only the app window — **there is no console window at all**: the exe is built as a windowed application, so not even a black rectangle flashes up;
* no administrator rights are needed: the exe manifest says `asInvoker`, and all changes are written to the current user's profile (`HKCU` on Windows, `~/.config` and `~/.local/share` on Linux). If Windows asks for administrator rights, it isn't the app — it's the shell or your antivirus; run the exe from an ordinary user folder rather than `C:\Program Files`;
* on first launch the system language is used, and you can change it from the list in the top-right corner of the window;
* the installer puts the app in `%LOCALAPPDATA%\Programs\BrouserGPUSwitch` without administrator rights, creates Start menu shortcuts, an "Uninstall GPU Switch" entry and an entry in the list of installed programs; the desktop shortcut is optional;
* in command-line modes (`BrouserGPUSwitch.exe --self-test`, `BrouserGPUSwitch.exe --diagnostics`) the app attaches to the console it was started from and prints its report there. The shell doesn't wait for a windowed program, so the prompt may come back before the report does; if that gets in the way, redirect the output to a file: `BrouserGPUSwitch.exe --diagnostics > report.txt`;
* settings and rollback work as usual, and the data lives in `%APPDATA%\BrowserGpuSwitch\`;
* the exe and the installer are built on Windows. On Linux, PyInstaller produces an executable with no extension, and it has to be built on Linux — that's what `build_linux.sh` is for.

### If the program won't start

**"Windows protected your PC"** (SmartScreen) — this isn't an error in the program. The file isn't signed with a paid code-signing certificate, so Windows warns about an unknown publisher. Click "More info" → "Run anyway". Shipping it publicly without that warning requires code signing.

**"Error. Could not create temporary directory!"** — this is how the one-file build behaves when the system or an antivirus blocks extraction into a temporary directory. In this version the one-file build extracts to `%LOCALAPPDATA%` instead of `%TEMP%`, so the error should be gone. If the restriction still kicks in, use the installer `BrouserGPUSwitch-Setup.exe` or the folder `dist\BrouserGPUSwitch\BrouserGPUSwitch.exe` — neither of them extracts anything. You can also build the folder by hand:

```bat
python -m PyInstaller --noconfirm --clean packaging\gpu-switch.spec
```

If you move the folder to another computer, copy it whole — the exe won't start without its support files next to it. The `BrouserGPUSwitch-Setup.exe` installer can be moved as a single file: it contains the folder inside itself. The `--silent` flag installs without asking anything (for example, `BrouserGPUSwitch-Setup.exe --silent --target=D:\Apps\GPUSwitch`).

## How to use it

1. Start the app; you can change the interface language right away from the list in the top-right corner of the window. Wait for detection of the system, browsers and graphics cards to finish.
2. In the "Select a browser detected on your PC" section, choose a browser.
3. In the "Which accelerator should it switch to?" section, the option currently in effect is already ticked.
4. In the "Which accelerator should it switch to?" section, choose the option you want.
5. If the browser is running, the app asks you to close it completely and click "Check again". The "Apply" button only becomes available once the browser's processes have exited.
6. Click "Apply". An "All set, launch your browser" window appears with a "Launch browser" button.
7. To undo the changes, click "Restore everything" and confirm.

## What exactly changes on the system

### Windows

The app uses the per-user Windows "Graphics settings" setting:

```
HKCU\Software\Microsoft\DirectX\UserGpuPreferences
```

* The value name is the full path to the browser's exe, for example `C:\Program Files\Google\Chrome\Application\chrome.exe`.
* The value data is a string such as `GpuPreference=2;`, where `0` is the default, `1` is power saving (integrated graphics) and `2` is high performance (discrete graphics).
* The other fields in the string (if there are any) are preserved.
* On rollback only what the app created is removed; if the value existed before it, the original contents are restored.

The change takes effect after the browser is fully restarted. This capability is supported by Windows 10 1803+ and works for applications that use the system GPU choice (Chromium-based browsers, Firefox and most games).

### Linux

A per-browser launcher is created for each browser:

* a wrapper script in the app's data directory (`~/.config/browser-gpu-switch/wrappers/`);
* an override `.desktop` file in `~/.local/share/applications/` marked with `X-BrowserGpuSwitch-Mode`.

The wrapper sets the environment variables and launches the original browser:

* for NVIDIA PRIME Render Offload:
  ```
  __NV_PRIME_RENDER_OFFLOAD=1
  __GLX_VENDOR_LIBRARY_NAME=nvidia
  __VK_LAYER_NV_optimus=NVIDIA_only
  ```
* for DRI_PRIME (AMD/Intel):
  ```
  DRI_PRIME=1
  ```

On rollback, only the wrapper and `.desktop` file created by the app are removed. Other overrides are left alone: if a third-party `.desktop` file already exists for the browser, the app refuses to overwrite it and says so.

## Where data is stored

* Windows: `%APPDATA%\BrowserGpuSwitch\`
* Linux: `~/.config/browser-gpu-switch/`
* To override the directory: the `BROWSER_GPU_SWITCH_HOME` environment variable.

The directory holds:

* `state.json` — details of the settings applied (needed for rollback, including after the app is restarted);
* `settings.json` — the selected interface language (created after the language is picked for the first time);
* `backups/` — backups of the files that were changed (Linux).

Deleting the directory by hand leaves the app unable to roll back changes — use "Restore everything" first.

## Command line

```
python main.py                     # обычный запуск
python main.py --mock              # демо-режим, ничего не меняет
python main.py --self-test         # самопроверка без окна, код возврата 0/1
python main.py --diagnostics       # технический отчёт: ОС, GPU, браузеры, процессы, откат
python main.py --ui-smoke-test     # скрытая проверка интерфейса
python main.py --screenshot-mode   # окно для скриншота (демо-данные)
python main.py --platform windows  # принудительно выбрать бэкенд
```

A built `BrouserGPUSwitch.exe` takes the same flags: `BrouserGPUSwitch.exe --self-test`, `BrouserGPUSwitch.exe --diagnostics`, `BrouserGPUSwitch.exe --mock` and the rest. The report is printed to the console the exe was started from; to save it to a file: `BrouserGPUSwitch.exe --diagnostics > report.txt`.

## Limitations and caveats

* The setting applies to the current user only. Other accounts are not affected.
* Windows: some programs ignore the system GPU setting and pick an adapter themselves. That's a Windows limitation, not the app's.
* Linux: switching works for launches through the `.desktop` file (application menu, dock). Starting from a terminal bypasses the `.desktop` file and uses the default settings.
* Linux + Wayland: behavior depends on the compositor and the driver; in some environments you have to sign in again for the change to apply.
* Flatpak/Snap versions of browsers may ignore environment variables because of their sandboxing.
* NVIDIA PRIME Render Offload requires the proprietary NVIDIA driver to be installed.
* "Default" doesn't select a specific graphics card — the operating system makes that call.
* The app installs no drivers and requires no reboot.
* The built `.exe` isn't code-signed: SmartScreen may show a "Windows protected your PC" warning ("More info" → "Run anyway"), and antivirus software occasionally flags PyInstaller builds as false positives. Shipping it publicly without warnings requires code signing.
* The one-file build extracts itself on every launch, but into `%LOCALAPPDATA%` rather than `%TEMP%`. If the system or an antivirus blocks even that, use the installer `BrouserGPUSwitch-Setup.exe` or the folder `dist\BrouserGPUSwitch\` — they extract nothing. `build_exe.bat` produces all the builds, and `build_linux.sh` handles Linux.
* No administrator rights are needed either to start it or to use it. The app changes only the current user's settings.

## Diagnostics

If the browser isn't found or the switch doesn't take effect:

```
python main.py --diagnostics
```

The report covers the OS, the list of GPUs, the browsers found with their paths, running processes, the switching options available, the changes applied and backend service information. Self-check:

```
python main.py --self-test
```

## Development

```
main.py                  точка входа CLI
app/interface.py         общий контракт (dataclasses и Protocol)
app/state.py             state.json, резервные копии, атомарная запись
app/main.py              логика CLI: self-test, diagnostics, smoke test
app/theme.py             оформление Windows 11: палитра, шрифты, ttk-стили, DPI
app/ui.py                интерфейс Tkinter (карточки, закреплённые кнопки)
app/i18n.py              переводы на 5 языков, выбор языка, settings.json
app/platforms/           бэкенды: windows, linux, mock, common
  common.py              запуск команд, чтение файлов
  mock.py                демонстрационный бэкенд
tests/                   unittest-тесты
docs/notes/              заметки по платформам
run.bat, run.sh          ярлыки запуска
packaging/gpu-switch.spec   сборка exe (PyInstaller): один файл и папка
packaging/version_info.txt  свойства файла BrouserGPUSwitch.exe (версия, описание)
build_exe.bat            сборка dist\BrouserGPUSwitch.exe и папки одной командой
devshots/                служебные скрипты для скриншотов документации
.github/workflows/       сборка exe на GitHub Actions
```

The styling lives in `app/theme.py`: the Windows 11 palette (`#F3F3F3` / white cards / `#0067C0` accent), the font stack `Segoe UI Variable Text → Segoe UI → …`, the spacing scale and every ttk style (cards, buttons, combobox, radio buttons, tables). Sizes are recalculated from the actual DPI; in `app/main.py` DPI awareness is enabled before the window is created, so text stays sharp at 125–150 %. Add new styles there, not in `app/ui.py`.

Tests:

```
python -m unittest discover -s tests -v
```

Building the exe directly, without the batch file:

```
python -m pip install --upgrade "pyinstaller>=6.0"
python -m PyInstaller --noconfirm --clean packaging/gpu-switch.spec
```

The `build_exe.bat` script does the same thing plus a self-check of the result. For your own exe icon, drop in `packaging/gpu-switch.ico` — the spec picks it up automatically.

Syntax check:

```
python -m compileall app
```

The tests don't touch real settings: the Windows backend is tested against a stub registry and a stub process list, and the Linux backend against stub sysfs/proc directories and a temporary home directory.

### Independent review

QA results, a trace of all ten requirements, test coverage and an honest list of limitations: [docs/qa-report.md](docs/qa-report.md).

Bottom line: 236 tests OK (1 skipped because of the environment), 44 integration tests, no functional defects found. Live writes to the Windows registry and checks of running processes can't be verified in a sandbox — that logic was validated against a stub registry and process list; on a regular machine one verification run is recommended.

## Version

1.0.0
