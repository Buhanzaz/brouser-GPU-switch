# QA report — GPU Switch (automated GPU switching script for a browser)

| Field | Value |
|---|---|
| Report date | 2026-10-26 |
| QA role | Independent QA engineer (task-4) |
| App version | 1.0.0 (see app/interface.py, APP_VERSION) |
| Deliverables | tests/test_integration.py (new, 44 tests), this report |
| Verdict | **PASS with sandbox limitations** — no functional defects found in the 10 customer requirements; requirements 7 and 8 are only partly verifiable on this host because the DSH sandbox denies live process inspection (WMI/tasklist) and HKCU registry writes. |

## 1. Environment

| Item | Value |
|---|---|
| OS | Windows 11 (10.0.22631), x86-64 |
| Python | 3.13 — C:\Python313\python.exe |
| Repository | C:\Users\buhanzaz\Desktop\automated-GPU-switching-script-for-a-browser |
| Shell | PowerShell ($env:PYTHONUTF8=1 prefix used for all commands) |
| Detected hardware (live) | Intel UHD Graphics 630 (integrated) + NVIDIA GeForce GTX 1050 Ti (discrete) |
| Detected browsers (live) | Firefox Developer Edition, Google Chrome, Microsoft Edge, Yandex |
| State file | %APPDATA%\BrowserGpuSwitch\state.json |
| GUI session | Real Windows desktop available; GUI driven only via --ui-smoke-test and in-process controller (no interactive windows left open) |
| Sandbox constraints | HKCU registry writes denied (PermissionError 13), WMI/tasklist process inspection denied, no WSL/real Linux, tempfile.mkdtemp dirs not removable, tests/.tmp* leftovers stuck by ACLs |

Known never-changed constraints from the customer brief: Russian UI, Windows + Linux support, no administrator rights, undo must restore the *original* system value even after repeated applies, Linux undo must never delete foreign .desktop overrides.

## 2. Artifacts

| Artifact | Path | Notes |
|---|---|---|
| New integration tests | [tests/test_integration.py](tests/test_integration.py) | stdlib unittest only, self-contained fakes, no dependency on teammates' test modules |
| QA report | docs/qa-report.md | this file |
| Full-suite evidence log | tests/.tmp/full-final.log | unittest verbose output of the final full run |
| Integration-suite evidence log | tests/.tmp/int-run3.log | unittest verbose output of the final integration run |

## 3. Commands executed (cwd = repository root, $env:PYTHONUTF8=1)

| # | Command | Exit | Result |
|---|---|---|---|
| 1 | C:\Python313\python.exe -m compileall -q -f app main.py | 0 | byte-compilation clean (final run after test file added) |
| 2 | C:\Python313\python.exe -m unittest discover -s tests -v | 0 | **218 tests, OK (skipped=1), 60.910 s** — final full run |
| 3 | C:\Python313\python.exe -m unittest tests.test_integration -v | 0 | **44 tests, OK, 7.979 s** — new file |
| 4 | C:\Python313\python.exe main.py --self-test | 0 | live Windows backend: **7/7 checks PASS** |
| 5 | C:\Python313\python.exe main.py --diagnostics | 0 | live detection report printed, ends with «конец отчёта.» |
| 6 | C:\Python313\python.exe main.py --self-test --mock | 0 | MockBackend: **7/7 checks PASS** |
| 7 | C:\Python313\python.exe main.py --ui-smoke-test | 0 | «смоук-тест интерфейса прошёл успешно.» |

Baseline before the new file: unittest discover = 174 tests OK (skipped=1) in 35.244 s; the final run adds the 44 integration tests (174 + 44 = 218). The single skip is pre-existing and environment-dependent (not in the new file; all 44 new tests executed).

Observed stderr noise in sandbox only: a single warning line "cannot create data directory ... [WinError 5]" when %APPDATA%\BrowserGpuSwitch is unwritable; it does not fail any command and is credited as sandbox noise (see D-1).

## 4. Requirement-by-requirement traceability (customer's 10 requirements)

Legend: **OK** = verified by automated test (+ live evidence where the sandbox allows); **PARTIAL** = logic verified against fakes/static checks, live hardware path blocked by sandbox.

| # | Requirement | Evidence (test → measured) | Status |
|---|---|---|---|
| 1 | OS detection | Live --diagnostics: platform line «Платформа: Windows (windows)», backend WindowsBackend. Tests: WindowsBackendIntegrationTests.test_os_detection (Windows 11, platform_key windows), LinuxBackendIntegrationTests.test_os_detection_from_os_release (fixture Ubuntu 24.04 LTS / 24.04 / X11), CliAcceptanceTests.test_diagnostics_live_windows, test_diagnostics_mock_lists_platform_gpus_browsers. Code: [app/platforms/windows.py](app/platforms/windows.py) os_info, [app/platforms/linux.py:528](app/platforms/linux.py#L528). | OK |
| 2 | Installed browsers detection | Live: 4 browsers via registry (Firefox Developer Edition, Chrome, Edge, Yandex; IE excluded). Tests: test_installed_browsers_detection (Windows fake registry: exactly those 4 names, supported, source registry, IE absent), Linux test_installed_browsers_detection (/usr/bin/google-chrome-stable, Firefox from .desktop), --diagnostics tests assert «браузеры (n)». Code: [app/platforms/windows.py](app/platforms/windows.py) list_browsers, [app/platforms/linux.py:918](app/platforms/linux.py#L918). | OK |
| 3 | Graphics chips detection | Live: 2 GPUs, Intel UHD 630 integrated + NVIDIA GTX 1050 Ti discrete; 2 GPU notes. Tests: test_graphics_chips_detection (Windows fake registry: 2 GPUs, kinds integrated/discrete), Linux test_graphics_chips_detection (fixture sysfs + NVIDIA proc info: GTX 1650, 8192 MB, kinds discrete/integrated). Code: [app/platforms/linux.py](app/platforms/linux.py) GPU scan, Windows registry GPU enumeration. | OK |
| 4 | Browser-selection window | --ui-smoke-test builds the real window hidden and validates the selector against the snapshot (exit 0). Tests: WindowsGuiAcceptanceTests.test_browser_selection_window_and_prompt — window title «GPU Switch», prompt text «Выберите браузер из обнаруженных на вашем ПК», combobox has exactly 4 entries, GPU table 2 rows, 3 accelerator radio buttons, system label contains «Windows 11». Code: [app/ui.py:367-381](app/ui.py#L367-L381) (browser section), [app/ui.py:275-313](app/ui.py#L275-L313) (UI build). | OK |
| 5 | Current accelerator shown after selecting a browser | Tests: test_current_accelerator_shown_after_selecting_browser — with GpuPreference=2; current label starts «Сейчас включён ускоритель:» and contains «Высокая производительность»; test_current_accelerator_reported_from_registry covers default / power-saving / high-performance / unknown (GpuPreference=9; → default). Code: [app/ui.py:918-943](app/ui.py#L918-L943), [app/platforms/windows.py](app/platforms/windows.py) current_option. | OK |
| 6 | Ability to choose a different accelerator | Tests: test_user_can_choose_a_different_accelerator — selecting windows:power-saving via the radio model changes selected option and enables Apply; test_options_offer_default_power_saving_high_performance — exactly the three expected option IDs; Linux test_options_include_nvidia_offload — default + NVIDIA offload options. Code: [app/ui.py:909-916](app/ui.py#L909-L916), [app/ui.py:426-452](app/ui.py#L426-L452). | OK |
| 7 | Prompt to close the browser and check it is really closed | Tests: Windows test_refuses_to_apply_while_browser_running — backend refuses, no registry write, no state entry when the process path is running; GUI test_running_browser_prompt_and_recheck — running warning visible, Apply disabled, apply returns failure, then after the process disappears «Проверить снова» hides the warning, enables Apply and reports «Браузер закрыт…»; Linux test_apply_writes_user_override_and_wrapper first half — running process blocks apply and no override file appears. Live process detection could not be exercised because WMI/tasklist are denied in the sandbox (see §6). Code: [app/ui.py:1016-1063](app/ui.py#L1016-L1063), is_browser_running in both backends. | PARTIAL (logic OK; live process check sandbox-blocked) |
| 8 | System setting actually changed (per-user, no admin) | Windows tests: test_apply_writes_per_user_registry_no_admin — exactly one write (HKCU, Software\Microsoft\DirectX\UserGpuPreferences, <chrome.exe>, "GpuPreference=2;"), state entry + pending change created; test_apply_survives_denied_registry_write — denial is handled gracefully with no state corruption. Linux tests: test_apply_writes_user_override_and_wrapper — writes only user-level .desktop override under ~/.local/share/applications and a wrapper under the app data dir, never touches root/system files (system .desktop byte-identical afterwards). Static: test_no_privilege_elevation_apis_in_source — no runas / ShellExecute / IsUserAnAdmin / requireAdministrator / pkexec in app/**/*.py or main.py. Live HKCU write is denied by the sandbox (PermissionError 13), so the actual live registry mutation could not be observed; the write target/format is verified against the fake registry seam. Code: [app/platforms/windows.py](app/platforms/windows.py) apply, [app/platforms/linux.py:1599](app/platforms/linux.py#L1599), key constant [app/interface.py:57](app/interface.py#L57). | PARTIAL (per-user design + logic OK; live registry write sandbox-blocked) |
| 9 | Success dialog with exact text «Все настроено, запустите браузер» and a launch button | Tests: test_ready_dialog_text_is_exact — READY_TITLE == "Все настроено, запустите браузер", LAUNCH_BUTTON == "Запустить браузер"; GUI test_apply_success_dialog_exact_text_and_launch_button — after a real apply through the controller the dialog is open, its title **and** its heading label equal the exact required text, the dialog contains the launch button and the chosen option label; invoking the launch button records backend.launch with the Chrome executable and shows the Russian launch notification. test_launch_browser_only_when_closed verifies launch succeeds only when the browser is closed. Code: [app/ui.py:67-71](app/ui.py#L67-L71), [app/ui.py:1144-1207](app/ui.py#L1144-L1207). | OK |
| 10 | Always-available «Вернуть всё назад» button | Tests: test_restore_everything_button_text (RESTORE_ALL_BUTTON == "Вернуть всё назад", confirm text present); GUI test_restore_everything_button_is_always_available — button enabled at startup and after an apply, restore undoes the registry value to the pre-apply state, clears pending rows and shows the «Готово» notification; test_restore_button_works_with_nothing_to_undo — works with no changes; backend test_undo_removes_value_that_did_not_exist_before; Linux test_undo_restores_original_and_removes_our_files, test_restore_all_without_changes_is_safe. Code: [app/ui.py:57](app/ui.py#L57), [app/ui.py:1082-1108](app/ui.py#L1082-L1108). | OK |

### Additional stated requirements

| Requirement | Evidence | Status |
|---|---|---|
| Russian UI | UiTextTests assert exact Russian strings and that every user-visible constant contains Cyrillic; live --diagnostics / --self-test / smoke output is Russian; friendly Russian failure messages are asserted in backend tests. | OK |
| Windows + Linux support | Windows verified live (read-only paths) + fake-world backend/GUI; Linux verified against a fixture filesystem world (sysfs, /proc, os-release, .desktop dirs, NVIDIA proc info). | OK (Linux not executed on a real distro) |
| No administrator rights | Static scan for elevation APIs = 0 hits; Windows writes target HKCU only; Linux writes are user-scoped. | OK |
| Undo correctness: second apply preserves the FIRST original value | Windows test_second_apply_preserves_first_original_value — pre-existing AppStatus=0;GpuPreference=1;, apply high-perf, apply power-saving (second apply), then restore returns exactly the original value and the state entry still holds the first original; Linux double-apply test asserts original_exec on the second entry equals the first. | OK |
| Linux safety: never delete foreign .desktop overrides | test_foreign_user_desktop_is_never_overwritten — apply refuses with «не будем…»/«Файл:» and leaves the foreign file byte-identical, state untouched; test_restore_keeps_foreign_file_but_removes_our_wrapper — restore removes our wrapper but keeps the foreign file, emits warning «изменён другой программой», clears state. | OK |
| StateStore robustness | test_corrupt_json_is_quarantined_not_fatal, test_non_object_entries_are_quarantined — corrupt/structurally invalid state.json is moved to state.json.corrupt-*, fresh state is used, app continues, new state persists. | OK |

## 5. New test coverage (tests/test_integration.py, 44 tests)

| Class | Tests | Focus |
|---|---|---|
| CliAcceptanceTests | 6 | real CLI subprocess: mock self-test, live self-test, mock/live diagnostics, UI smoke test, unknown-argument handling |
| UiTextTests | 4 | exact requirement-9/10 texts, Russian UI, no-elevation static scan |
| WindowsBackendIntegrationTests | 13 | OS/GPU/browser detection, options, current accelerator parsing, apply (HKCU only), running-browser guard, restore, double-apply undo, denied-write resilience, launch, platform-scoped state |
| LinuxBackendIntegrationTests | 10 | os-release/sysfs/browsers detection, options, user override + wrapper + backup + state, running-browser guard, undo/double apply, foreign-file safety on apply and restore, apply-default undo |
| StateStoreIntegrationTests | 3 | persistence roundtrip, corrupt JSON quarantine, invalid structure quarantine |
| WindowsGuiAcceptanceTests | 8 | requirements 4–10 through GpuSwitchApp against the fake world: selection window, current accelerator label, option choice, close-browser prompt/recheck, exact success dialog + launch button, always-available restore, empty restore, clean shutdown |

Design notes: fakes are self-contained in the new file (Windows registry/process/system + Linux fixture world) so the QA suite does not depend on other teammates' test modules; temporary dirs are created under tests/.tmp because the sandbox can't remove tempfile.mkdtemp dirs; GUI tests are guarded by skipUnless(Tk available) and use the controller's public inspection helpers.

## 6. What could not be verified in this sandbox (honest limitations)

1. **Requirement 8 live mutation**: HKCU\Software\Microsoft\DirectX\UserGpuPreferences writes are denied (PermissionError 13). Verified: exact key/value format, per-user scope, value preservation and undo logic against the fake registry. Not verified: that Windows actually honours the written GpuPreference=2; value after a real browser restart. Needs one acceptance run on a normal (non-sandboxed) Windows account.
2. **Requirement 7 live process detection**: WMI and tasklist are denied, so live browser-running detection (running_pids) could not be exercised against real processes; only fixture processes were used. On the live --diagnostics run the program degraded gracefully (prints «неизвестно/нет данных» notes instead of crashing).
3. **Linux live execution**: no Linux host or WSL. Linux backend was verified fixture-only: sysfs GPU discovery, /proc process table, os-release, .desktop parsing, applying/undoing user overrides. Distro/desktop-environment variability (GNOME/KDE, Wayland, Flatpak wrappers, permission bits) remains untested on real Linux.
4. **POSIX execute bit for the wrapper**: the Windows filesystem cannot store POSIX permission bits, so the runtime 0o755 check is conditional; the intent is additionally asserted statically (_write_atomic(wrapper_path, script, 0o755) in app/platforms/linux.py:1499).
5. **Interactive GUI**: per QA instructions the real GUI was not driven interactively; startup/teardown was verified by --ui-smoke-test, and complete requirement flows (4–10) were driven through the real GpuSwitchApp controller with hidden tk.Tk() windows and a fake backend.

## 7. Defects and observations

No functional defect was found in app/, main.py, README.md, or the existing tests during this QA pass. The following observations are recorded for completeness; none blocks acceptance.

| ID | Severity | Area | Description | Reproduction / evidence |
|---|---|---|---|---|
| D-1 | Low (environment noise, previously reported) | app/state.py:80-82 | Under the DSH sandbox %APPDATA%\BrowserGpuSwitch is unwritable; StateStore logs "cannot create data directory ... [WinError 5]" to stderr and sets writable = False (code comment explicitly avoids a traceback). Commands still exit 0 and functionality degrades gracefully. Normal users have a writable %APPDATA%, so this is sandbox-only noise. | C:\Python313\python.exe main.py --diagnostics 2>&1 from the repo — one warning line on stderr. |
| D-2 | Info | live diagnostics | In the sandbox, browser running-state and some process data show as unavailable («неизвестно») because WMI/tasklist are denied. This is correct graceful degradation, not a defect. | live --diagnostics output, notes section. |
| D-3 | Info | tests/.tmp* | Leftover temporary directories are stuck because of sandbox ACLs; they are test hygiene only and not part of the product. | tests/.tmp* directories exist, owned by earlier test runs. |
| D-4 | Info | app/main.py help text | The Tkinter-missing hint prints «sudo apt install python3-tk» — this is an installation hint for the user, not an elevation performed by the app. The static no-admin scan therefore targets elevation APIs, not the word sudo. | app/main.py _print_tkinter_missing, final line. |

## 8. Residual risks

- **OS regression risk on live Windows**: only one Windows build (11 22631) and one hardware pair were available. Registry layout is the official per-user DirectX preference key, but older Windows 10 builds should get a short smoke run.
- **Linux desktop variability**: .desktop override is per-user and intentionally conservative (refuses foreign files), yet GNOME/KDE/Flatpak launchers may cache desktop entries; a real-distro check (update-desktop-database, XDG data dirs) is advisable before release.
- **NVIDIA offload**: verified only structurally (env vars/exec wrapper in fixture). Real behaviour depends on the installed proprietary driver and the browser's own GPU process handling.
- **Requirement 8 end-to-end acceptance**: pending one non-sandboxed Windows run (apply → restart browser → Windows GPU preference shows the expected GPU).
- **Undo after external edits**: foreign-file safety is implemented and tested, but a user editing our generated wrapper/override outside the app can only be detected for the .desktop override (warning path); wrapper content is regenerated on restore.

## 9. Verdict

**PASS with limitations.** All ten customer requirements are implemented and have automated evidence; requirements 1–6, 9 and 10 are fully verified (including live read-only Windows detection), requirements 7 and 8 have their logic verified end-to-end against backend fakes but the live mutation/inspection paths are blocked by the sandbox. Undo correctness (second apply preserving the first original value), Russian UI, no-admin design, and Linux foreign-.desktop safety are all covered by passing tests. Final regression state: **218 tests OK (skipped=1)** and compilation clean; no product defects found in this QA pass.
