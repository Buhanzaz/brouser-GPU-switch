# UI and CLI notes

Scope of this note: the window in `app/ui.py`, the logic/CLI layer in `app/main.py`,
the launcher `main.py` and the tests in `tests/test_ui_smoke.py`.

## Architecture in one paragraph

`app/main.py` is GUI-free on import: it only decides the mode, creates a backend
through `app.platforms.get_backend()` and, for the GUI modes, imports Tkinter and
`app.ui.GpuSwitchApp` lazily inside `run_gui()`. The window never talks to the
platform modules directly - it receives any object implementing the backend protocol
(`app/interface.py`) and only uses protocol methods. Detection and all potentially
slow backend calls run on a worker thread; results return through a
`queue.Queue` and are applied in the Tk thread from an `after()` poller, so the
window stays responsive and shows "Обнаружение..." while the backend works.

## Window layout (top to bottom)

1. Header with the app name and a short Russian description.
2. "Система" - OS name/version/architecture plus host name.
3. "Видеокарты" - table rows (one row per detected GPU, or a "Не найдено" placeholder).
4. "Браузер" - read-only combobox with the detected browsers; below it the summary
   "Сейчас включён ускоритель: ..." and the note shown when the default accelerator is active.
5. "Ускоритель" - one radiobutton per option; unavailable/current variants are disabled.
6. Action row: "Применить", "Проверить снова", "Вернуть настройки браузера" (per-browser
   restore, shown only when the selected browser has a pending change),
   "Вернуть всё назад", "Обновить".
7. "Ожидающие изменения" - pending rows plus the placeholder "Нет изменений.".
8. Status line at the bottom.

Running-browser flow: selecting a browser that is running shows a warning block with the
PIDs and the hint to close the browser, disables "Применить", and offers "Проверить снова".
After a successful apply the modal dialog "Все настроено, запустите браузер" appears with
the "Запустить браузер" button; the pending-change table below shows what will be rolled
back by "Вернуть всё назад".

## The ten UI requirements

1. Works for any backend implementing the protocol; tests use `get_backend("mock")`.
2. OS/browser/GPU detection happens off the Tk thread (worker + queue + `after()`).
3. The selected browser's current accelerator is always visible ("Сейчас включён ускоритель: ...").
4. The user can pick another accelerator; the current one is preselected where possible.
5. A running browser is detected before applying; the user is asked to close it and
   "Проверить снова" re-checks without restarting the application.
6. Apply uses a per-user setting only (the backend is responsible for HKCU / user config);
   the UI never asks for admin rights.
7. The exact completion text is "Все настроено, запустите браузер" in a modal dialog,
   with a launch button that starts the selected browser.
8. "Вернуть всё назад" is always available (even with no pending changes) and restores
   everything the application changed.
9. All user-visible strings are Russian and friendly; technical diagnostics stay in the
   backend's `diagnostics()` and in `--diagnostics` output.
10. When detection finishes with nothing found, the window still renders placeholders
    ("Не найдено", "Обнаруженные браузеры не найдены.") instead of crashing.

## Text constants (exact strings)

`READY_TITLE = "Все настроено, запустите браузер"`
`PENDING_EMPTY = "Нет изменений."`
`NOT_FOUND = "Не найдено"`
`NO_BROWSERS_SUMMARY = "Обнаруженные браузеры не найдены."`

The ready dialog title doubles as its headline; `ready_dialog_message()` returns it so
tests can assert the exact wording.

## CLI modes (`main.py`)

| Flag | Behaviour | Exit code |
| --- | --- | --- |
| (none) | Normal GUI; detects the current platform | 0 |
| `--self-test` | Headless consistency check of a backend (pass/fail lines) | 0 all pass, 1 otherwise |
| `--diagnostics` | Headless full text report | 0 |
| `--ui-smoke-test` | Builds the real window, checks it, closes it | 0, 2 if Tk is missing |
| `--screenshot-mode` | GUI with mock data, fixed geometry, preselected Chrome, ready dialog (for docs screenshots) | 0 |
| `--mock` | Force `MockBackend` (demo data) | - |
| `--platform windows|linux|mock` | Force a platform backend | - |

Mode flags are mutually exclusive. `--ui-smoke-test` deliberately defaults to the mock
backend unless `--platform` is given, so it is deterministic on any machine;
`--screenshot-mode` always forces mock data. `--self-test` and `--diagnostics`
use the real platform unless overridden. Missing Tkinter is reported with a friendly
Russian message and exit code 2, never a traceback.

## Testing

```
C:Python313python.exe -m unittest discover -s tests -p "test_ui_smoke.py" -v
C:Python313python.exe -m unittest discover -s tests -v
```

The module has 19 tests: 10 headless (self-test/diagnostics/argument helpers) and 9 GUI
tests skipped automatically when Tk or a display is unavailable. GUI tests build the real
window with `GpuSwitchApp(root, backend)` against `MockBackend`, inject `confirm`/`notify`
callbacks, and use the public inspection helpers (`gpu_rows()`, `pending_rows()`,
`option_labels()`, `ready_dialog_open()`, ...) instead of reaching into Tk internals.
Temp directories are created with `Path.mkdir()` under `tests/.tmp` because
`tempfile.mkdtemp()` directories are not always writable/removable under the sandbox.

Live check performed on this Windows machine: `main.py --mock --screenshot-mode`
opened a visible window titled "GPU Switch" (verified through `EnumWindows`) and kept
running until terminated, so the Lead's screenshot flow (`scratch/screenshot_gui.py`)
can capture it.

## Known limitations / open questions

- `app/state.py` prints a traceback to stderr when the user data directory
  (`%APPDATA%BrowserGpuSwitch`) cannot be created; the application still works, but the
  self-test output is noisy on machines where that path is denied. State module is
  Lead-owned, reported to the Lead.
- `--ui-smoke-test` using mock by default is a deliberate choice; it can be pointed at
  a real platform with `--platform windows`.
- The Linux GUI path is covered only by fixtures here (no live Linux host in this
  environment).
- Screenshot geometry `1000x760+30+30` targets the 1920x1080 display used for the docs
  screenshot.
