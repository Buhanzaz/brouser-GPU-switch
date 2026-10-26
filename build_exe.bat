@echo off
rem Build BrouserGPUSwitch (Python and Tkinter are NOT needed on the target
rem machine).  Needs Python 3.9+ and internet access once, to install
rem PyInstaller.  Three artefacts are produced:
rem   dist\BrouserGPUSwitch.exe                  - single self-contained file
rem   dist\BrouserGPUSwitch\BrouserGPUSwitch.exe - folder build (no unpacking)
rem   dist\BrouserGPUSwitch-Setup.exe            - installer for the folder build
rem None of them asks for administrator rights.
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"

where python >nul 2>nul
if not errorlevel 1 (
    set "PY=python"
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python 3 not found. Install Python 3.9+ from https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set "PY=py -3"
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
    echo Python 3.9 or newer is required.
    pause
    exit /b 1
)

%PY% -c "import PyInstaller, sys; sys.exit(0 if int(PyInstaller.__version__.split('.')[0]) >= 6 else 1)" >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller ^(one-time, about 10 MB^)...
    %PY% -m pip install --upgrade "pyinstaller>=6.0"
    if errorlevel 1 (
        echo Could not install PyInstaller. Check the internet connection and try again.
        pause
        exit /b 1
    )
)

echo Building BrouserGPUSwitch ...
%PY% -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\gpu-switch.spec
if errorlevel 1 (
    echo.
    echo Build failed. See the messages above.
    pause
    exit /b 1
)

echo.
echo Checking that the built program starts ...
dist\BrouserGPUSwitch.exe --self-test >nul
if errorlevel 1 (
    echo.
    echo The single-file exe failed its self-test. Run "dist\BrouserGPUSwitch.exe --self-test" to see why.
    pause
    exit /b 1
)
if exist "dist\BrouserGPUSwitch\BrouserGPUSwitch.exe" (
    "dist\BrouserGPUSwitch\BrouserGPUSwitch.exe" --self-test >nul
    if errorlevel 1 (
        echo.
        echo The folder build failed its self-test.
        pause
        exit /b 1
    )
)

echo.
echo Building the installer ...
%PY% -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\installer.spec
if errorlevel 1 (
    echo.
    echo Installer build failed. See the messages above.
    pause
    exit /b 1
)

if exist "dist\BrouserGPUSwitch-Setup.exe" (
    echo.
    echo Checking that the installer really installs ...
    if exist "build\install-test" rmdir /s /q "build\install-test"
    dist\BrouserGPUSwitch-Setup.exe --silent --target=build\install-test --no-shortcuts --no-registry >nul
    if errorlevel 1 (
        echo.
        echo The installer failed. Stop antivirus interference and try again.
        pause
        exit /b 1
    )
    "build\install-test\BrouserGPUSwitch.exe" --self-test >nul
    if errorlevel 1 (
        echo.
        echo The installed copy failed its self-test.
        pause
        exit /b 1
    )
)

echo.
echo Done.
for %%F in ("dist\BrouserGPUSwitch.exe") do echo Single file: %%~zF bytes - %CD%\dist\BrouserGPUSwitch.exe
if exist "dist\BrouserGPUSwitch\BrouserGPUSwitch.exe" (
    echo Folder build: %CD%\dist\BrouserGPUSwitch\BrouserGPUSwitch.exe
)
if exist "dist\BrouserGPUSwitch-Setup.exe" (
    for %%F in ("dist\BrouserGPUSwitch-Setup.exe") do echo Installer: %%~zF bytes - %CD%\dist\BrouserGPUSwitch-Setup.exe
)
echo Windows 10/11, no Python required, no administrator rights required.
echo A double-click opens only the program window: the exe has no console.
endlocal
