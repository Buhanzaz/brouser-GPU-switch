# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ``dist/BrouserGPUSwitch-Setup.exe``.

The installer is a tiny Tkinter window that carries the whole application as
data: the folder build ``dist/BrouserGPUSwitch`` is embedded as ``payload/``.
Run ``build_exe.bat`` (or the GitHub workflow) so that folder exists first.

The result is one self-contained file: double-click, and the program is
installed into ``%LOCALAPPDATA%\\Programs\\BrouserGPUSwitch`` without asking for
administrator rights.  Unpacking uses ``%LOCALAPPDATA%`` rather than the system
temp folder, for the same reason as the application's single-file build.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
PAYLOAD = ROOT / "dist" / "BrouserGPUSwitch"
VERSION = ROOT / "packaging" / "installer_version_info.txt"

if not (PAYLOAD / "BrouserGPUSwitch.exe").is_file():
    raise SystemExit(
        "dist/BrouserGPUSwitch is missing: build the application folder build first "
        "(python -m PyInstaller packaging/gpu-switch.spec)"
    )

a = Analysis(
    [str(ROOT / "packaging" / "installer.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(PAYLOAD), "payload")],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "tkinter.filedialog",
        "winreg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy",
        "PIL",
        "pytest",
        "setuptools",
        "pip",
        "pydoc",
        "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BrouserGPUSwitch-Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=r"%LOCALAPPDATA%",
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(VERSION),
)
