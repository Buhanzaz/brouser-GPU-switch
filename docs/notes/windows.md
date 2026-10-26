# Windows backend — implementation notes

Implementation: `app/platforms/windows.py`. Tests: `tests/test_windows.py` (69 unittest cases).

## Scope

- Implements `PlatformBackend` from `app/interface.py` for Windows 10/11 (`platform_key = WINDOWS`).
- Manages the per-application GPU preference that Windows exposes in Settings -> System -> Display -> Graphics and that the NVIDIA/AMD control panels write.
- Per-user only: every write goes to HKCU, administrator rights are never required.
- Standard library only. `winreg` is imported lazily and guarded, so the module still imports and byte-compiles on non-Windows hosts (registry reads then return no data).
- Public backend methods never raise: failures become `ApplyResult.failure` / empty lists and are remembered for `diagnostics()`.

## The system setting

- Key: `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` (`WINDOWS_GPU_PREFS_KEY` in `app/interface.py`).
- Value name: the full path of the browser executable, e.g. `C:\Program Files\Google\Chrome\Application\chrome.exe`; value type REG_SZ.
- Value data: semicolon-separated `Key=Value;` pairs. The managed field is `GpuPreference`:
  - `GpuPreference=0` — let Windows decide (the default),
  - `GpuPreference=1` — power saving (integrated GPU),
  - `GpuPreference=2` — high performance (discrete GPU).
- Other fields in the same value (for example `AppStatus=0;`) are preserved. `_compose_preference` rewrites only `GpuPreference` and always keeps the trailing `;`.
- Choosing the default option does not write `GpuPreference=0`: if an original value is known it is restored or deleted, and without state the value is deleted. That is exactly what Windows does when the user removes a per-app preference in Settings.
- Reads of HKLM are allowed; all writes target HKCU only.

## Module layout

- `WindowsRegistry` — guarded `winreg` wrapper. API: `get_value`, `get_string`, `list_values`, `list_subkeys`, `set_string`, `delete_value`; hives are plain strings `HKLM`/`HKCU`. Reads return `None`/`[]` on error, writes propagate `OSError` so the backend can render a friendly Russian message; `available`/`last_error` expose the state.
- `RunningProcess(pid, path, name)` — one process from the snapshot.
- `WindowsProcessProvider` — process enumeration through `ctypes` (see Process detection). Public: `processes()`/`snapshot()`, `running_paths()`, `pids()`, `diagnostics()`, `last_error`; never raises.
- `WindowsSystem` — OS information and side effects: `windows_version()`, `architecture()`, `hostname()`, `file_exists()`, `launch(command) -> pid`.
- `WindowsBackend(registry=None, process_provider=None, state=None, system=None)` — the protocol implementation. Every collaborator is injectable; the defaults are the live classes above plus `StateStore()` (tests pass fakes and a state store in a temporary directory).
- Pure helpers: `_normcase`, `_as_text`, `_coerce_int`, `_split_command`, `_command_executable`, `_engine_for`, `_parse_preference`, `_compose_preference`, `_preference_for_option`, `_slug`, `_clean_client_name`, `_popen_detached`; classification helpers `_classify_vendor`, `_classify_kind`, `_memory_mb`, `_parse_pci`.
- `_guard(operation, func, fallback)` wraps every public method: an unexpected exception is logged, appended to the error ring (last 20) and the fallback value is returned.

## GPU detection (`list_gpus`)

- Root: `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}` (`GPU_CLASS_KEY`). The root `Class` value must be `Display`.
- Enumerate subkeys `0000`, `0001`, ... and read `DriverDesc`, `ProviderName`, `MatchingDeviceId`, `DriverVersion`, and `HardwareInformation\qwMemorySize` / `HardwareInformation\MemorySize`.
- Memory: `qwMemorySize` (QWORD) first, then `MemorySize` as DWORD or as 4-byte little-endian BINARY; bytes are converted to MB (integer division). Missing value gives 0.
- Vendor from `ProviderName` + `MatchingDeviceId` + `DriverDesc`: `intel`, `nvidia`, `amd` (AMD/ATI), `microsoft` (Basic Render Driver) and `other`.
- Kind: Intel -> `integrated`; NVIDIA/AMD -> `discrete`; Microsoft Basic Render Driver -> `virtual`; unknown otherwise.
- `pci_address` is taken from `MatchingDeviceId`, e.g. `PCI\VEN_10DE&DEV_1C8C` (uppercased). The stable id is `windows:gpu:<ven>:<dev>` (lowercase), e.g. `windows:gpu:10de:1c8c`.
- Ordering: integrated first, then discrete, then virtual, then unknown; the order is stable.

## Browser detection (`list_browsers`)

- Sources: `HKLM\SOFTWARE\Clients\StartMenuInternet`, `HKLM\SOFTWARE\WOW6432Node\Clients\StartMenuInternet`, `HKCU\SOFTWARE\Clients\StartMenuInternet` (in this order).
- For each subkey: default value = display name; `shell\open\command` default = command line; optional `Version`.
- Executable is parsed from the command line (quoted path or the first `.exe` token), so arguments such as `--single-argument %1` stay in `launch_command` but not in `executable`.
- Skipped: `iexplore.exe` (Internet Explorer is deliberately excluded), executables that do not exist on disk, duplicates by normalised executable path.
- `id` = `windows:` + slug of the StartMenuInternet key, e.g. `windows:google-chrome`, `windows:firefox-ca9422711ae1a81c`, `windows:microsoft-edge`, `windows:yandex`.
- `name` comes from the registry display value (`Firefox Developer Edition`, `Google Chrome`, ...); `engine` is `chromium` for Chrome/Edge/Yandex/Brave/Opera/Vivaldi/Chromium and `gecko` for Firefox; `process_names` contains the lowercased exe basename; `source` is `registry`.
- Fallback (only when the registry yields no browsers): the well-known install paths of Chrome, Edge, Mozilla Firefox, Firefox Developer Edition, Yandex Browser, Brave, Opera, Vivaldi and Chromium under `ProgramFiles`, `ProgramFiles(x86)`, `ProgramW6432`, `LOCALAPPDATA`; a candidate is accepted only when the file exists.
- Result is sorted by display name (case-insensitive).

## Options (`list_options`)

Always exactly three `GpuOption` entries, even when no GPU is detected:

- `windows:default` — «По умолчанию — Windows выбирает сам», payload `{"preference": 0}`.
- `windows:power-saving` — «Энергосбережение — <integrated GPU name>», payload `{"preference": 1}`.
- `windows:high-performance` — «Высокая производительность — <discrete GPU name>», payload `{"preference": 2}`.

When the matching chip is missing the labels fall back to «встроенная видеокарта» / «дискретная видеокарта»; the ids and payloads never change.

## Current option (`current_option`)

- Reads the HKCU value whose name matches the browser executable. Matching is case-insensitive (`_normcase`); an existing value name with real-world casing is reused on write.
- `GpuPreference=N` is parsed with a regex; 1 -> power saving, 2 -> high performance, 0 / missing / unparsable -> default. The returned object is one of the options from `list_options()`.

## Process detection

- `tasklist` and WMI are often blocked (they are blocked in the development sandbox), therefore the provider uses `ctypes`: `CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)`, `Process32FirstW`/`Process32NextW` with `PROCESSENTRY32W`, then `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `QueryFullProcessImageNameW` for the full image path. Handles are closed in `finally`; every failure degrades to an empty list plus `last_error`.
- `is_browser_running` / `running_pids` match either the full executable path or the basename (case-insensitive) and also honour `Browser.process_names`. A browser without an executable is never considered running.

## Apply flow and undo semantics

`apply(browser, option)` performs these steps:

1. Resolve the option against `list_options()` (`unknown id -> failure`); a custom option is accepted only if its payload contains a valid preference.
2. Require a non-empty browser executable path.
3. Refuse while the browser is running: «Браузер ещё запущен. Закройте его полностью и повторите попытку.»
4. Read the state entry `windows:<normalised exe path>`.
5. Capture the ORIGINAL value: if the entry already has `original_exists`/`original_data`, keep it; otherwise capture the current registry data (`None` -> `original_exists = false`). Consequence: a second apply without restore keeps the FIRST original, so undo returns to the true pre-application state.
6. Compose the new data (other fields preserved), write it to HKCU and store the state entry.
7. Default option: restore the captured original (write it back or delete the value) and remove the state entry; without a state entry just delete the value and report success even when nothing was set.

State entry fields: `platform`, `browser_id`, `browser_name`, `option_id`, `option_label`, `applied_at` (`now_iso()`), `description`, `original_exists`, `original_data`, `value_name`, `executable`, `gpu_preference`.

A successful apply returns a Russian message and `details` with the registry path, the value name/data and the reminder that a full browser restart is required. Registry `OSError`s become `ApplyResult.failure` with the exception type/message in `details`; anything unexpected is caught by `_guard`.

## Restore (`restore_all`, `restore_browser`)

- Only entries whose `platform` equals `windows` are touched; entries of other backends (Linux/mock) are ignored.
- If `original_exists` is true the stored `original_data` is written back; otherwise the value is deleted. The state entry is removed only after a successful write.
- `restore_all()` restores every Windows entry: with no entries it succeeds («Возвращать нечего: изменений нет.»). Per-entry failures are reported as `warnings` while the successfully restored browsers are listed; if nothing could be restored the result is a failure with details.
- `restore_browser(browser)` does the same for one state key and succeeds when there is nothing to restore.

## Launch (`launch`)

- Uses `Browser.command` (`launch_command` or `executable`), drops empty parts and shell placeholders (`%1`, `%*`, ...) when all trailing arguments are placeholders.
- Refuses when the executable is missing or the browser is already running; on success returns `LaunchResult(ok=True, ..., pid=...)`.
- `WindowsSystem.launch` starts the process with `subprocess.Popen(..., creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)` so the browser survives closing this app. The backend never raises.

## Notes and diagnostics

- `notes()` returns four Russian hints: per-user setting without administrator rights; the change needs a full close and restart of the browser; Windows 10/11 uses the system GpuPreference parameter; if the browser is running, close all windows and background processes and retry.
- `diagnostics()` returns a multi-line report: backend name, Windows version pretty string, registry availability (read yes, write only HKCU), GPU class key, registry warning, GPUs (name, vendor, kind, driver, memory, PCI, id), browsers (name, executable, engine, source), options, visible process count + warning, pending changes, state file path and the last recorded errors.

## Tests

Command (repository root):

```powershell
C:\Python313\python.exe -m unittest discover -s tests -p "test_windows.py" -v
```

- 69 unittest cases, all passing on the target Windows machine.
- Injection: `FakeRegistry` (dict-backed, case-insensitive, optional write/delete errors), `FakeProcessProvider` (only `running_paths()`/`pids()`), `FakeSystem` (Windows version, arch, hostname, `file_exists`, launch recorder) and a real `StateStore` in a unique directory under `tests/.tmp`.
- Coverage highlights: GPU parsing/classification/memory/PCI/sorting; command-line parsing (quotes, arguments), IE exclusion, dedupe, well-known fallback; options and preference parsing; process matching incl. case-insensitivity and provider failures; apply (new value, default restores/deletes, double apply keeps first original, independent browsers, `applied_at`); restore (write-back, delete, registry failure, other-platform entries ignored, persistence across backend instances); launch; notes and diagnostics.
- `LiveRegistryReadOnlyTests` run on Windows only and read the real machine (GPU class, HKCU preferences) — never writing.

### Sandbox note on temporary directories

In the development sandbox `tempfile.mkdtemp()` directories reject file writes (they get a restrictive ACL), while plain directories created inside the workspace work. The tests therefore create plain unique directories under `tests/.tmp` (`pathlib.Path.mkdir` + `uuid4`) and remove them in `tearDown`. Empty `win-test-*` directories left over from the first runs cannot be deleted from inside the sandbox and may remain in `tests/.tmp`.

## Known limitations and open questions

- Live apply/restore cannot be exercised in the development sandbox: HKCU writes fail with `PermissionError 13`. Registry writes are covered by fakes only; a manual smoke test on a normal user session is recommended.
- The setting is per user (HKCU) by design; there is no machine-wide/admin mode.
- A browser restart is required; Chromium builds may keep background processes, which `running_pids` reports.
- Internet Explorer is excluded by requirement. Other registered browsers are listed, but older engines may ignore the DirectX preference.
- With several integrated or discrete GPUs only the first of each kind is used for the option labels.
- Detection relies on standard StartMenuInternet registration; portable or unregistered browsers are offered only when they live in a well-known path.
- No long-lived handles: every registry and process handle is closed immediately, so `close()` is a no-op.
