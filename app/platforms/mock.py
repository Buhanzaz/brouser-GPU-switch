"""In-memory backend used by --mock (screenshots, UI development, tests).

The mock backend never reads or writes anything on the real machine.
"""

from __future__ import annotations

import sys
from typing import Dict, List

from app.interface import (
    MOCK,
    MOCK_OPTION_DEFAULT,
    MOCK_OPTION_HIGH_PERFORMANCE,
    MOCK_OPTION_POWER_SAVING,
    ApplyResult,
    Browser,
    Gpu,
    GpuOption,
    LaunchResult,
    OsInfo,
    PendingChange,
    now_iso,
)


def _demo_browsers() -> List[Browser]:
    if sys.platform.startswith("win"):
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        firefox = r"C:\Program Files\Firefox Developer Edition\firefox.exe"
        yandex = r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe"
    else:
        chrome = "/usr/bin/google-chrome-stable"
        edge = "/usr/bin/microsoft-edge-stable"
        firefox = "/usr/bin/firefox"
        yandex = "/usr/bin/yandex-browser"

    return [
        Browser(
            id="mock:chrome",
            name="Google Chrome",
            executable=chrome,
            launch_command=(chrome,),
            engine="chromium",
            version="131.0",
            source="mock",
        ),
        Browser(
            id="mock:edge",
            name="Microsoft Edge",
            executable=edge,
            launch_command=(edge,),
            engine="chromium",
            version="131.0",
            source="mock",
        ),
        Browser(
            id="mock:firefox",
            name="Firefox Developer Edition",
            executable=firefox,
            launch_command=(firefox,),
            engine="firefox",
            version="134.0",
            source="mock",
        ),
        Browser(
            id="mock:yandex",
            name="Yandex Browser",
            executable=yandex,
            launch_command=(yandex,),
            engine="chromium",
            version="24.12",
            source="mock",
        ),
    ]


class MockBackend:
    """Demo backend with a simulated two-GPU machine."""

    platform_key = MOCK

    def __init__(self, simulate_running: bool = True) -> None:
        self._browsers = _demo_browsers()
        self._gpus = [
            Gpu(
                id="mock:intel",
                name="Intel(R) UHD Graphics 630",
                vendor="intel",
                kind="integrated",
                driver="31.0.101.2140",
            ),
            Gpu(
                id="mock:nvidia",
                name="NVIDIA GeForce GTX 1050 Ti",
                vendor="nvidia",
                kind="discrete",
                driver="32.0.15.8157",
                memory_mb=4096,
            ),
        ]
        self._options = [
            GpuOption(
                id=MOCK_OPTION_DEFAULT,
                label="По умолчанию — Windows выбирает сам",
                description="Браузер работает с той видеокартой, которую выберет система.",
                kind="auto",
            ),
            GpuOption(
                id=MOCK_OPTION_POWER_SAVING,
                label="Энергосбережение — Intel(R) UHD Graphics 630",
                description="Встроенная графика: меньше энергопотребление, слабее 3D.",
                kind="integrated",
                gpu_id="mock:intel",
            ),
            GpuOption(
                id=MOCK_OPTION_HIGH_PERFORMANCE,
                label="Высокая производительность — NVIDIA GeForce GTX 1050 Ti",
                description="Дискретная видеокарта: быстрее 3D, больше расход батареи.",
                kind="discrete",
                gpu_id="mock:nvidia",
            ),
        ]
        self._initial: Dict[str, str] = {"mock:chrome": MOCK_OPTION_HIGH_PERFORMANCE}
        self._applied: Dict[str, PendingChange] = {}
        self._running: Dict[str, bool] = {}
        if simulate_running:
            # A running browser is useful for demonstrating the check.
            self._running["mock:firefox"] = True

    # -- read API ----------------------------------------------------------
    def os_info(self) -> OsInfo:
        return OsInfo(
            platform_key=MOCK,
            name="Демо-режим",
            version="Windows 11 · 24H2",
            arch="x86_64",
            hostname="demo-pc",
        )

    def list_gpus(self) -> List[Gpu]:
        return list(self._gpus)

    def list_browsers(self) -> List[Browser]:
        return list(self._browsers)

    def list_options(self) -> List[GpuOption]:
        return list(self._options)

    def _option_by_id(self, option_id: str) -> GpuOption:
        for option in self._options:
            if option.id == option_id:
                return option
        return self._options[0]

    def current_option(self, browser: Browser) -> GpuOption:
        applied = self._applied.get(browser.id)
        if applied is not None:
            return self._option_by_id(applied.option_id)
        return self._option_by_id(self._initial.get(browser.id, MOCK_OPTION_DEFAULT))

    def notes(self) -> List[str]:
        return [
            "Демонстрационный режим: реальные настройки компьютера не меняются.",
            "Запуск браузера и изменения настроек имитируются.",
        ]

    def is_browser_running(self, browser: Browser) -> bool:
        return bool(self._running.get(browser.id))

    def running_pids(self, browser: Browser) -> List[int]:
        return [4242, 4243] if self.is_browser_running(browser) else []

    # -- write API ---------------------------------------------------------
    def apply(self, browser: Browser, option: GpuOption) -> ApplyResult:
        if option.id not in {item.id for item in self._options}:
            return ApplyResult.failure("Неизвестный вариант настройки графики.")
        if self.is_browser_running(browser):
            return ApplyResult.failure(
                "Браузер ещё запущен. Закройте его и повторите попытку."
            )
        if option.id == MOCK_OPTION_DEFAULT:
            self._applied.pop(browser.id, None)
            return ApplyResult.success(
                "Для браузера " + browser.name + " возвращены настройки по умолчанию (демо)."
            )

        change = PendingChange(
            key="mock:" + browser.id,
            platform=MOCK,
            browser_id=browser.id,
            browser_name=browser.name,
            option_id=option.id,
            option_label=option.label,
            applied_at=now_iso(),
            description=browser.name + ": " + option.label,
        )
        self._applied[browser.id] = change
        return ApplyResult.success(
            "Настройка сохранена (демо): " + option.label,
            details="MockBackend: nothing was modified on disk.",
        )

    def pending_changes(self) -> List[PendingChange]:
        return list(self._applied.values())

    def restore_all(self) -> ApplyResult:
        count = len(self._applied)
        self._applied.clear()
        if count == 0:
            return ApplyResult.success("Возвращать нечего: изменений нет.")
        return ApplyResult.success(
            "Демо-настройки возвращены к исходным (" + str(count) + ")."
        )

    def restore_browser(self, browser: Browser) -> ApplyResult:
        if browser.id in self._applied:
            self._applied.pop(browser.id, None)
            return ApplyResult.success("Настройки браузера " + browser.name + " возвращены (демо).")
        return ApplyResult.success("Для этого браузера изменений нет.")

    def launch(self, browser: Browser) -> LaunchResult:
        if not browser.command:
            return LaunchResult(ok=False, message="Не удалось определить команду запуска.")
        return LaunchResult(
            ok=True,
            message=browser.name + " запущен (демо-режим, процесс не создавался).",
        )

    def diagnostics(self) -> str:
        return (
            "Backend: MockBackend\n"
            "System access: none (demo mode)\n"
            "Browsers: " + str(len(self._browsers)) + "\n"
            "GPUs: " + str(len(self._gpus)) + "\n"
            "Applied changes: " + str(len(self._applied))
        )

    def close(self) -> None:
        self._applied.clear()
