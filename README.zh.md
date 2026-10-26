# GPU Switch

**语言:** [Русский](README.md) · [English](README.en.md) · [中文](README.zh.md) · [Español](README.es.md) · [Deutsch](README.de.md)

一款小巧的 Windows 与 Linux 桌面程序，用于为选定的浏览器切换图形加速器（显卡）。所有操作都在当前用户权限范围内完成，无需管理员权限。界面采用 Windows 11 风格：细边框卡片、Segoe UI Variable 字体、系统强调色。

```
Windows 10/11 · Linux · Python 3.9+ · Tkinter · без сторонних библиотек
Установщик BrouserGPUSwitch-Setup.exe, один файл BrouserGPUSwitch.exe
и архив для Linux собираются build_exe.bat / build_linux.sh
```

## 为什么需要

在配备双显卡（集成 Intel/AMD 与独立 NVIDIA/AMD）的笔记本和台式机上，浏览器默认可能运行在性能较弱的集成显卡上。GPU Switch 可让 Chrome、Edge、Firefox、Yandex Browser 等浏览器强制使用独立显卡，同样也能轻松还原。

## 功能

1. 识别操作系统（Windows 10/11 或 Linux）、其版本与架构。
2. 查找已安装的浏览器（Windows 下通过 StartMenuInternet 注册表和已知路径；Linux 下通过 .desktop 文件）。
3. 识别显卡芯片：集成显卡、独立显卡和虚拟显卡。
4. 显示选择窗口：「请从本机检测到的浏览器中选择」。
5. 在加速器列表中预选该浏览器当前生效的选项，并将其标记为已选中。
6. 可选择要切换到的加速器。
7. 提示关闭浏览器，并通过进程确认其确实已关闭。
8. 修改系统设置——仅针对当前用户。
9. 切换完成后显示「全部设置完成，请启动浏览器」窗口，并带有启动该浏览器的按钮。
10. 始终可用的「还原全部设置」按钮会撤销程序所做的全部更改。

## 界面预览

![GPU Switch 主窗口](docs/gui-main.png)

*主窗口：「系统」「显卡」「浏览器」卡片、加速器选择，以及固定在底部的强调色「应用」按钮。*

![应用设置后的窗口](docs/gui-success.png)

*切换设置后：「全部设置完成，请启动浏览器」，并带有启动浏览器的按钮。*

## 语言

界面已翻译为五种语言：**俄语**、**英语**、**中文**、**西班牙语**、**德语**。

语言可在主窗口右上角的下拉列表中选择——紧邻版本号。首次启动时会使用系统语言（或此前保存的语言）。选择后窗口会立即以新语言重新启动，所选语言会保存在程序数据目录中的 `settings.json` 里（参见「数据存放位置」），并在后续启动时沿用。

只有程序的界面元素会被翻译。显卡名称、浏览器名称和版本属于系统数据，保持原样。命令行辅助模式（`--self-test`、`--diagnostics`）始终以俄语输出报告。

## 环境要求

* Windows 10（1803 及更高版本）或 Windows 11，或带 X11/Wayland 的 Linux。
* Python 3.9+ 并带 Tkinter。
  * Windows：[python.org](https://www.python.org/downloads/) —— 安装程序已包含 Tkinter。
  * Debian/Ubuntu: `sudo apt install python3-tk`
  * Fedora: `sudo dnf install python3-tkinter`
  * Arch: `sudo pacman -S tk`
* 无需任何第三方 Python 包。
* 使用现成的 `BrouserGPUSwitch.exe` 无需 Python 和 Tkinter——参见「现成的安装程序与构建产物」。

## 运行

Windows：

```bat
run.bat
```

或通过命令行：

```bat
py -3 main.py
```

Linux：

```sh
chmod +x run.sh
./run.sh
```

或：

```sh
python3 main.py
```

演示模式（不会改动电脑上的任何内容，仅显示演示数据）：

```
python main.py --mock
```

## 现成的安装程序与构建产物（无需 Python）

自行构建（仅在安装 PyInstaller 时需要一次联网）：

```bat
build_exe.bat
```

脚本会检查 Python 3.9+，必要时安装 PyInstaller，并构建三个版本：

* `dist\BrouserGPUSwitch-Setup.exe` —— 安装程序。可选择安装目录，将程序安装到 `%LOCALAPPDATA%\Programs\BrouserGPUSwitch`（无需管理员权限），在「开始」菜单中创建快捷方式，可按需在桌面创建，添加「卸载 GPU Switch」，并在 Windows 已安装程序列表中登记；
* `dist\BrouserGPUSwitch.exe` —— 单文件，约 11–12 MB，像普通 exe 一样复制和传输；
* `dist\BrouserGPUSwitch\BrouserGPUSwitch.exe` —— 一个包含附属文件的文件夹：无需解压任何内容，因此即使单文件构建被拦截，它也能运行。

安装程序内部包含 `dist\BrouserGPUSwitch` 文件夹，因此必须在它之后构建——`build_exe.bat` 会自动处理。所有版本都会在构建结束时通过自检，安装程序还会额外执行一次静默安装试运行。

针对 Linux，项目中提供了 `build_linux.sh`：它会构建 `dist/BrouserGPUSwitch-linux-x86_64.tar.gz` —— 一个含程序文件夹、`install.sh`、`uninstall.sh` 和 `.desktop` 快捷方式的压缩包。用户解压后运行 `./install.sh`；程序安装到 `~/.local`，无需 root：

```bash
chmod +x build_linux.sh
./build_linux.sh
```

如果项目托管在 GitHub 上，这些都会自动完成：**Actions** 标签页 → **build** → **Run workflow**。构建好的安装程序、单文件构建、文件夹压缩包和 Linux 压缩包会出现在该次运行附加的文件（artifact）中。推送形如 `v1.0.0` 的标签时，它们会附加到 release 上——这样就可以通过链接分发给用户。

构建出的文件的运行表现：

* 双击时只会打开程序窗口——**完全没有控制台窗口**：exe 以窗口应用方式构建，因此连黑色矩形都不会闪现；
* 无需管理员权限：exe 清单中为 `asInvoker`，所有更改都写入当前用户的配置目录（Windows 下为 `HKCU`，Linux 下为 `~/.config` 和 `~/.local/share`）。如果 Windows 弹出管理员权限请求，那并非来自本程序，而是外壳/杀毒软件；请从普通用户目录运行 exe，而不要从 `C:\Program Files` 运行；
* 首次启动时使用系统语言，可在窗口右上角的列表中更改；
* 安装程序无需管理员权限即可将程序安装到 `%LOCALAPPDATA%\Programs\BrouserGPUSwitch`，在「开始」菜单中创建快捷方式、「卸载 GPU Switch」条目以及已安装程序列表中的记录；桌面快捷方式为可选项；
* 在命令行模式下（`BrouserGPUSwitch.exe --self-test`、`BrouserGPUSwitch.exe --diagnostics`），程序会连接到启动它的控制台并在其中打印报告。由于外壳不会等待窗口程序，命令提示符可能先于报告返回；如果这造成不便，可将输出重定向到文件：`BrouserGPUSwitch.exe --diagnostics > report.txt`；
* 设置与回滚照常工作，数据位于 `%APPDATA%\BrowserGpuSwitch\`；
* exe 和安装程序均针对 Windows 构建。在 Linux 上 PyInstaller 会生成不带扩展名的可执行文件，且必须在 Linux 上构建——为此提供了 `build_linux.sh`。

### 如果程序无法启动

**「Windows 已保护你的电脑」**（SmartScreen）——这不是程序错误。该文件未使用付费的代码签名证书签名，因此 Windows 会提示未知发布者。点击「更多信息」→「仍要运行」。若要在公开分发时不再出现该提示，需要进行代码签名。

**「Error. Could not create temporary directory!」**——这是单文件构建在系统或杀毒软件禁止解压到临时目录时的表现。在当前版本中，单文件构建不再解压到 `%TEMP%`，而是解压到 `%LOCALAPPDATA%`，因此该错误应当不再出现。如果限制依然生效，请使用安装程序 `BrouserGPUSwitch-Setup.exe` 或文件夹版本 `dist\BrouserGPUSwitch\BrouserGPUSwitch.exe`——两者都不会解压任何内容。该文件夹也可以手动构建：

```bat
python -m PyInstaller --noconfirm --clean packaging\gpu-switch.spec
```

如果要转移文件夹到另一台电脑，请整体复制——缺少旁边附属文件的 exe 无法启动。安装程序 `BrouserGPUSwitch-Setup.exe` 可以作为单个文件转移：它内部已包含该文件夹。`--silent` 参数可在无交互的情况下安装程序（例如 `BrouserGPUSwitch-Setup.exe --silent --target=D:\Apps\GPUSwitch`）。

## 使用方法

1. 启动程序；界面语言可随时在窗口右上角的下拉列表中更改。等待系统、浏览器和显卡检测完成。
2. 在「请从本机检测到的浏览器中选择」区域选择浏览器。
3. 在「要切换到哪个加速器？」区域中，当前生效的选项已被选中。
4. 在「要切换到哪个加速器？」区域中选择所需的选项。
5. 如果浏览器正在运行，程序会提示将其完全关闭，然后点击「重新检查」。「应用」按钮只有在浏览器进程结束后才会变为可用。
6. 点击「应用」。将出现「全部设置完成，请启动浏览器」窗口，其中带有「启动浏览器」按钮。
7. 如需撤销更改，点击「还原全部设置」并确认操作。

## 具体修改了系统中的什么

### Windows

使用的是 Windows 的用户级设置「图形设置」：

```
HKCU\Software\Microsoft\DirectX\UserGpuPreferences
```

* 值名称——浏览器 exe 文件的完整路径，例如 `C:\Program Files\Google\Chrome\Application\chrome.exe`。
* 值数据——形如 `GpuPreference=2;` 的字符串，其中 `0` 表示默认，`1` 表示节能（集成显卡），`2` 表示高性能（独立显卡）。
* 字符串中的其他字段（如果存在）会保留。
* 回滚时只删除由本程序创建的内容；如果该值在程序运行前已存在，则恢复其原始内容。

更改在浏览器完全重启后生效。此功能受 Windows 10 1803+ 支持，适用于使用系统 GPU 选择的应用程序（Chromium 系浏览器、Firefox 以及大多数游戏）。

### Linux

为每个浏览器创建一个专属启动项：

* 程序数据目录中的包装脚本（`~/.config/browser-gpu-switch/wrappers/`）；
* `~/.local/share/applications/` 中带有 `X-BrowserGpuSwitch-Mode` 标记的覆盖 `.desktop` 文件。

包装脚本会设置环境变量并启动原始浏览器：

* 对于 NVIDIA PRIME Render Offload：
  ```
  __NV_PRIME_RENDER_OFFLOAD=1
  __GLX_VENDOR_LIBRARY_NAME=nvidia
  __VK_LAYER_NV_optimus=NVIDIA_only
  ```
* 对于 DRI_PRIME（AMD/Intel）：
  ```
  DRI_PRIME=1
  ```

回滚时只删除由程序创建的包装脚本和 `.desktop` 文件。不会触碰他人的覆盖文件：如果该浏览器已存在第三方的 `.desktop` 文件，程序将拒绝覆盖并给出提示。

## 数据存放位置

* Windows: `%APPDATA%\BrowserGpuSwitch\`
* Linux: `~/.config/browser-gpu-switch/`
* 覆盖目录：环境变量 `BROWSER_GPU_SWITCH_HOME`。

该目录中包含：

* `state.json` —— 已应用设置的信息（回滚时需要，包括程序重启之后）；
* `settings.json` —— 所选界面语言（首次选择语言后创建）；
* `backups/` —— 已修改文件的备份（Linux）。

手动删除该目录会使程序无法回滚更改——请先使用「还原全部设置」。

## 命令行

```
python main.py                     # обычный запуск
python main.py --mock              # демо-режим, ничего не меняет
python main.py --self-test         # самопроверка без окна, код возврата 0/1
python main.py --diagnostics       # технический отчёт: ОС, GPU, браузеры, процессы, откат
python main.py --ui-smoke-test     # скрытая проверка интерфейса
python main.py --screenshot-mode   # окно для скриншота (демо-данные)
python main.py --platform windows  # принудительно выбрать бэкенд
```

构建后的 `BrouserGPUSwitch.exe` 具有相同的选项：`BrouserGPUSwitch.exe --self-test`、`BrouserGPUSwitch.exe --diagnostics`、`BrouserGPUSwitch.exe --mock` 等。报告会打印到启动该 exe 的控制台；如需保存到文件：`BrouserGPUSwitch.exe --diagnostics > report.txt`。

## 限制与注意事项

* 该设置仅对当前用户生效，不影响其他账户。
* Windows：部分程序会忽略系统 GPU 设置而自行选择适配器。这是 Windows 的限制，而非程序的限制。
* Linux：切换仅对通过 `.desktop` 文件启动的方式生效（应用菜单、Dock）。绕过 `.desktop` 从终端启动时会使用默认设置。
* Linux + Wayland：行为取决于合成器和驱动；在某些环境中需要重新登录会话才能生效。
* Flatpak/Snap 版本的浏览器可能因沙箱而忽略环境变量。
* NVIDIA PRIME Render Offload 需要已安装 NVIDIA 专有驱动。
* 「默认」不会选择具体的显卡——由操作系统决定。
* 程序不安装驱动，也不需要重启。
* 构建出的 `.exe` 未进行代码签名：SmartScreen 可能显示「Windows 已保护你的电脑」警告（「更多信息」→「仍要运行」），杀毒软件有时也会对 PyInstaller 构建产生误报。若要在公开分发时不再出现警告，需要进行代码签名。
* 单文件构建每次启动都会解压，但不是解压到 `%TEMP%`，而是 `%LOCALAPPDATA%`。如果系统或杀毒软件连这个也禁止，请使用安装程序 `BrouserGPUSwitch-Setup.exe` 或文件夹 `dist\BrouserGPUSwitch\`——它们都不解压任何内容。所有构建均由 `build_exe.bat` 完成，Linux 版本则由 `build_linux.sh` 完成。
* 无论运行还是工作都不需要管理员权限。程序只修改当前用户的设置。

## 诊断

如果找不到浏览器或切换不生效：

```
python main.py --diagnostics
```

报告包含操作系统、GPU 列表、检测到的浏览器及其路径、运行中的进程、可用的切换选项、已应用的更改以及后端的辅助信息。自检：

```
python main.py --self-test
```

## 开发

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

界面样式集中在 `app/theme.py`：其中包含 Windows 11 调色板（`#F3F3F3` / 白色卡片 / 强调色 `#0067C0`）、字体栈 `Segoe UI Variable Text → Segoe UI → …`、间距刻度和所有 ttk 样式（卡片、按钮、下拉框、单选按钮、表格）。尺寸会根据实际 DPI 重新计算；在 `app/main.py` 中会在创建窗口前启用 DPI 感知，以便在 125–150% 缩放下文字依然清晰。新增样式请加在那里，而不是 `app/ui.py`。

测试：

```
python -m unittest discover -s tests -v
```

直接构建 exe（不使用 bat 文件）：

```
python -m pip install --upgrade "pyinstaller>=6.0"
python -m PyInstaller --noconfirm --clean packaging/gpu-switch.spec
```

`build_exe.bat` 脚本完成同样的工作，并额外对结果进行自检。为 exe 使用自定义图标：将 `packaging/gpu-switch.ico` 放好——spec 会自动采用它。

语法检查：

```
python -m compileall app
```

测试不会修改真实设置：Windows 后端使用模拟注册表和模拟进程列表进行测试，Linux 后端使用模拟的 sysfs/proc 目录和临时主目录进行测试。

### 独立验证

QA 检查结果、全部十项需求的追踪、测试覆盖率以及如实的限制清单：[docs/qa-report.md](docs/qa-report.md)。

结论：236 项测试通过（1 项因环境跳过），44 项集成测试，未发现功能性缺陷。对 Windows 注册表的实际写入以及在沙箱中检查运行进程无法验证——相关逻辑已基于模拟的注册表和进程列表进行验证；在普通机器上建议做一次实际运行验证。

## 版本

1.0.0
