# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for BrouserGPUSwitch (no Python needed on the target PC).

Build with the bundled script (installs PyInstaller if it is missing)::

    build_exe.bat

or directly::

    python -m PyInstaller --noconfirm --clean packaging/gpu-switch.spec

Two artefacts are produced from one analysis:

* ``dist/BrouserGPUSwitch.exe`` - one self-contained file.  It unpacks itself
  on every start, but not into the system temp folder: it unpacks under
  ``%LOCALAPPDATA%`` instead, which always exists and is usually allowed where
  ``%TEMP%`` is blocked by antivirus policy.
* ``dist/BrouserGPUSwitch/BrouserGPUSwitch.exe`` - the same program as a plain
  folder.  Nothing is unpacked at all, so this variant always starts.

Neither variant requests administrator rights: the embedded manifest uses the
default ``asInvoker`` level.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
ICON = ROOT / "packaging" / "gpu-switch.ico"
VERSION = ROOT / "packaging" / "version_info.txt"

# The platform backends are imported inside functions (app/platforms/__init__.py
# picks one at run time), so static analysis cannot see them and they have to be
# listed explicitly.  tkinter submodules are listed for the same reason: app/ui.py
# imports them lazily inside the GUI entry points.
HIDDEN_IMPORTS = [
    "app.platforms.windows",
    "app.platforms.linux",
    "app.platforms.mock",
    "tkinter",
    "tkinter.ttk",
    "tkinter.font",
    "tkinter.messagebox",
    "tkinter.filedialog",
]

# Nothing in the program imports these; excluding them keeps the exe small.
EXCLUDES = [
    "numpy",
    "PIL",
    "pytest",
    "setuptools",
    "pip",
    "pydoc",
    "unittest",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

COMMON = dict(
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=r"%LOCALAPPDATA%",
    # Windowed (GUI-subsystem) build: Windows never opens a console window, so
    # a double-click shows only the program window - not even the brief flash a
    # console build would produce.  Command-line modes (--self-test and friends)
    # attach to the caller's console from main.py instead.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.is_file() else None,
    version=str(VERSION),
)

# 1) Single-file build: dist/BrouserGPUSwitch.exe
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="BrouserGPUSwitch", **COMMON)

# 2) Folder build: dist/BrouserGPUSwitch/BrouserGPUSwitch.exe (no temp unpacking)
exe_onedir = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BrouserGPUSwitch",
    **COMMON,
)
coll = COLLECT(
    exe_onedir,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BrouserGPUSwitch",
)
