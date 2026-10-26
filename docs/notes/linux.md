# Linux backend — implementation notes

`app/platforms/linux.py` implements the frozen `PlatformBackend` contract from
`app/interface.py` for Linux. It is written for a regular user: no root, no
`sudo`, no package installation, and nothing outside the user's home directory
is touched. Detection reads files only (`/etc/os-release`, sysfs, `/proc`,
`.desktop` entries); no shell tools are required.

Related files:

* `app/platforms/linux.py` — the backend (`LinuxBackend`, `platform_key = linux`).
* `tests/test_linux.py` — 86 stdlib `unittest` tests, all runnable on Windows.
* `docs/notes/linux.md` — this document.

## Stable option ids

The UI matches options by id, so these ids from `app/interface.py` are the API:

| id | meaning | environment |
| --- | --- | --- |
| `linux:default` | system picks the GPU (always available) | — |
| `linux:nvidia-offload` | NVIDIA PRIME Render Offload | `__NV_PRIME_RENDER_OFFLOAD=1`, `__GLX_VENDOR_LIBRARY_NAME=nvidia`, `__VK_LAYER_NV_optimus=NVIDIA_only` |
| `linux:dri-prime` | AMD/Mesa PRIME (DRI_PRIME) | `DRI_PRIME=1` |

`linux:nvidia-offload` is offered only when a non-virtual NVIDIA GPU is present.
`linux:dri-prime` is offered when a non-virtual AMD GPU (integrated APU or
discrete) is present. Virtual-only machines (QXL, virtio, VMware, VirtualBox)
get just `linux:default`. Labels name the real detected chip, e.g.
`"Дискретная NVIDIA — NVIDIA GeForce GTX 1650"`.

Two public helpers exist so the UI does not need to know about payloads:

* `backend.option_env(option) -> Dict[str, str]` — environment to launch with.
* `backend.describe_launch(option) -> str` — short Russian sentence about the launch.

`list_options()` always returns `linux:default` first; `current_option(browser)`
reads the marker from our desktop override and falls back to the default option.

## Detection

### OS (`os_info()`)

Reads `/etc/os-release` (then `/usr/lib/os-release`), key `PRETTY_NAME`, else
`NAME` + `VERSION_ID`. Platform key is `linux`, arch from `platform.machine()`,
hostname from `socket.gethostname()`, and `session` is `Wayland` / `X11`
(from `XDG_SESSION_TYPE`, fallback `XDG_SESSION_DESKTOP` / `XDG_CURRENT_DESKTOP`).
Added to `notes()` so the UI can warn that Wayland may ignore GPU switching.

### GPUs (`list_gpus()`)

Scan `/sys/class/drm/card*/device` (the `card*-*` connectors are skipped) and
then `/sys/bus/pci/devices` for display-class PCI functions that have no DRM
card. Per device:

* `vendor` — `0x10de` NVIDIA, `0x8086` Intel, `0x1002` AMD, `0x1af4` /
  `0x15ad` / `0x1234` / `0x80ee` virtual, other ids kept as-is;
* `driver` — name of the `driver` symlink target (also tries the `uevent`
  `DRIVER=` line);
* `boot_vga` — marks the primary/integrated chip, which is used to classify
  Intel / AMD APUs as `integrated`;
* `mem_info_vram_total` — converted to `memory_mb`;
* PCI slot from `uevent PCI_SLOT_NAME` (fallback: the symlink name);
* NVIDIA model name from `/proc/driver/nvidia/gpus/<slot>/information`
  (`Model: ...`), if present, else `product_name`-style files, else a
  vendor-derived name.

`kind` is `integrated`, `discrete`, `virtual` or `unknown`; known virtual
drivers (`virtio_gpu`, `qxl`, `vmwgfx`, `bochs-drm`, `vboxvideo`, ...) and
virtual vendors are classified as `virtual`. Results are sorted integrated
first, then discrete, then virtual.

### Browsers (`list_browsers()`)

Scans these directories in order:

1. `/usr/share/applications`
2. `/usr/local/share/applications`
3. `~/.local/share/applications`
4. `~/.local/share/applications` (XDG_DATA_HOME redirect target, if different)
5. `/var/lib/flatpak/exports/share/applications`
6. `~/.local/share/flatpak/exports/share/applications`

Each `*.desktop` file is parsed for `[Desktop Entry]`: `Name`, `Exec`,
`TryExec`, `NoDisplay`, `Hidden`, `Type` and `OnlyShowIn` / `NotShowIn`
(resolved against the current desktop; with no session information entries are
assumed visible). An entry is kept when its executable matches a known browser
prefix (google-chrome, chromium, microsoft-edge/msedge, firefox, brave, opera,
vivaldi, yandex-browser) or it has `WebBrowser` in `Categories`, and the
resolved executable actually exists (`which()` is injected for tests; flatpak
entries use `flatpak run <app-id>`). Files we create ourselves (they carry the
`X-BrowserGpuSwitch-Mode` marker) are ignored, as are hidden/NoDisplay entries
and broken `TryExec`.

Field codes (`%u`, `%U`, `%f`, `%F`, `%%`, ...) are stripped from `Exec`;
environment prefixes like `FOO=bar /usr/bin/browser` are understood. Duplicate
browser ids prefer the user-local file (that is the file we would override).
`Browser.id` is the desktop file name without `.desktop`;
`Browser.desktop_file` keeps the full system file path; `source` is `desktop`,
`flatpak` or `manual`; `process_names` come from the executable basename.

## How a change is applied

Per-user, file based, no admin:

1. Refuse while the browser is running (see below) and refuse unknown or
   currently unavailable option ids. Writing `linux:default` means "undo for
   this browser".
2. Refuse to touch a foreign file: if `~/.local/share/applications/<id>.desktop`
   exists **without** our `X-BrowserGpuSwitch-Mode` marker, the user's own
   shortcut is left alone and the reason is reported.
3. Write a launcher script `<data_dir>/wrappers/<safe-id>-<mode>.sh` (mode
   `0755`, starts with `# Generated by GPU Switch`). It exports the variables
   for the chosen mode and `exec`s the original command with `"$@"`:
   `#!/bin/sh` / `export __NV_PRIME_RENDER_OFFLOAD=1` / ... /
   `exec /usr/bin/google-chrome-stable "$@"` (the command is shell-quoted with
   `shlex.join`, so paths with spaces work too).
4. Save a backup of the original desktop text via
   `StateStore.backup_file(key, "original.desktop")` (file only, never
   overwritten), then write the override
   `~/.local/share/applications/<id>.desktop`: a copy of the system entry with
   `Exec=` pointing at the wrapper and these marker keys added:
   `X-BrowserGpuSwitch-Mode` (option id), `X-BrowserGpuSwitch-Original-Exec`,
   `X-BrowserGpuSwitch-Original-Desktop`, `X-BrowserGpuSwitch-App`,
   `X-BrowserGpuSwitch-Desktop-Id`.
5. Persist one `StateStore` entry under key `linux:<desktop id>` with
   `platform`, `browser_id`, `browser_name`, `option_id`, `option_label`,
   `applied_at` (`now_iso()`), `description`, `override_path`,
   `wrapper_path`, `created_by_us`, `original_exec`, `desktop_id`.

Applying a second mode for the same browser keeps the **first** recorded
original data (so undo is always against the original system entry), rewrites the
override, and deletes the previous wrapper only when it carries our marker.

All file writes are atomic (temp file + `os.replace`, fsync) so a crash cannot
leave a half-written shortcut. The system directories are never modified.

## Undo / restore

`restore_all()` and `restore_browser(browser)` only look at entries whose
`platform` is `linux` (other platforms' entries are ignored). For each entry:

* delete the override only when it exists **and** still carries our marker —
  if another program rewrote it, it is kept and a warning is reported;
* delete the wrapper at the recorded path and any
  `<data_dir>/wrappers/<id>-*.sh` candidate only when it starts with
  `# Generated by GPU Switch`;
* delete the backup directory via `StateStore.remove_backup_dir(key)`;
* delete the state entry.

If `created_by_us` is not true, nothing is deleted. Missing files are tolerated
(the state entry is still removed), so a second restore is a successful no-op.
The Russian messages report how many browsers were restored and mention kept or
already-deleted files.

## Process detection

`running_pids(browser)` scans `/proc/<pid>/exe` (`os.readlink`, tolerating
` (deleted)`) and `/proc/<pid>/cmdline` tokens; `comm` is a last-resort check.
A process matches when the executable basename or any cmdline token basename is
one of the browser's `process_names`, or when a flatpak app id appears in the
command line. Permission errors, vanished PIDs and a missing `/proc` are
swallowed. `is_browser_running()` is a thin wrapper over `running_pids()`.

## Launch

`launch(browser)` starts `browser.command` with the environment of the
currently applied option for that browser, `start_new_session=True`,
`close_fds=True`, stdio to `DEVNULL` and `cwd=home`, so the app can be closed
right after. Failures return a `LaunchResult` with a friendly Russian message;
exceptions never escape.

## Error handling

Every public method is defensive: it catches `Exception`, records the incident
in an in-memory list (`diagnostics()` prints the last 20 under `Errors:`) and
returns a safe value (`ApplyResult.failure` / empty list / default option /
`False` / `""`). `diagnostics()` prints backend, OS, session, home/data paths,
sysfs/proc presence, GPUs, browsers, options and pending changes, which is what
we ask users to paste into a bug report. `notes()` returns friendly Russian
hints: no admin needed, changes apply on next launch from the app menu, Wayland
caveat, Flatpak caveat, "no GPU found", and "undo removes only our files".

## Testing on a machine without Linux

There is no WSL and no real `/sys` or `/proc` in the CI/sandbox, so the backend
takes every environment path through the constructor:`home`, `data_dir`,
`state`, `sysfs_root`, `proc_root`, `desktop_dirs`, `applications_dir`,
`which`, `os_release_path`, `environ`. Production defaults are used only when
an argument is omitted.

`tests/test_linux.py` builds a fake world in a temporary tree and injects it:

* fake `/etc/os-release` (Ubuntu 24.04), fake `sysfs` with DRM cards,
  connectors, render nodes, audio PCI devices, `uevent` files and NVIDIA
  `/proc/driver/nvidia` info, fake `/proc` with pid directories
  (`cmdline`, `comm`, `exe`), fake home with system/user/flatpak desktop
  entries, and a real `StateStore` in the temp data dir;
* executables are fake paths registered in a `which()` replacement, so no
  real programs run; `Popen` is mocked for launch tests and
  `os.listdir` is mocked for a permission-error test.

Notable Windows/sandbox details (they affect only the tests, not the backend):

* PCI slot names contain `:`, which is illegal in Windows file names, so the
  fixture directories replace `:` with `_` for `/sys/bus/pci/devices/...` and
  `/proc/driver/nvidia/gpus/...`; the backend learns the real address from the
  `uevent` `PCI_SLOT_NAME=` content. For robustness
  `_nvidia_model()` also tries the underscored spelling on any OS (first
  readable path wins).
* The sandbox denies writing to system temp with the needed ACLs, so the tests
  create their temporary tree under `tests/.tmp` (plain `mkdir`) and remove it
  in `tearDownModule()`; `tempfile` on this host produces folders that cannot be
  listed or deleted afterwards.
* Windows here cannot create symlinks, so fixtures write plain files for
  `driver` and `exe` (the backend reads the link target when it is a symlink,
  else the file content), and the "driver symlink is followed" test is skipped.

Run the module:

```
C:\Python313\python.exe -m unittest tests.test_linux -v
```

Result on the Windows dev box: `Ran 86 tests ... OK (skipped=1)` (skip is the
symlink test). Full suite with discovery:

```
C:\Python313\python.exe -m unittest discover -s tests -v
```

## Known limitations

* Switching is per user and only affects launches from the desktop menu; an
  already running browser keeps its GPU.
* Wayland may ignore the environment variables — the app suggests the X11
  session.
* Flatpak's sandbox may strip the variables; the app points to
  `chrome://gpu` / `about:support` for verification.
* Only XDG desktop environments are handled; a manually launched
  `/usr/bin/firefox` from a terminal bypasses the wrapper.
* NVIDIA Optimus setups need a working proprietary driver; PRIME render
  offload is not implemented for Wayland-only compositors.
* `DRI_PRIME=1` assumes the Mesa driver numbering (the user may need
  `DRI_PRIME=pci-0000_01_00_0` on some systems — not implemented yet).
