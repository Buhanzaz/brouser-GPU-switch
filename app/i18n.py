"""Localisation for the GPU Switch window.

The UI is available in five languages: Russian, English, Chinese, Spanish and
German.  Russian strings double as the canonical product wording, so the rest
of the application (the platform backends, the state file and the tests) keeps
producing Russian labels; :func:`translate_option_label` and
:func:`translate_option_description` translate the backend-provided option
text on the fly for the other four languages.

Only the window is translated: the command-line modes (``--self-test``,
``--diagnostics``) stay Russian because they are aimed at developers.
"""

from __future__ import annotations

import json
import locale
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.state import default_data_dir

DEFAULT_LANGUAGE = "ru"
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("ru", "en", "zh", "es", "de")

#: Language code -> native name shown in the language chooser.
LANGUAGES: Tuple[Tuple[str, str], ...] = (
    ("ru", "Русский"),
    ("en", "English"),
    ("zh", "中文"),
    ("es", "Español"),
    ("de", "Deutsch"),
)

SETTINGS_FILE_NAME = "settings.json"

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": {
        "subtitle": "Переключение графического ускорителя для браузера",
        "version_label": "релиз {version}",
        "system": "Система",
        "gpus": "Видеокарты",
        "browser": "Браузер",
        "browser_prompt": "Выберите браузер из обнаруженных на вашем ПК",
        "current_prefix": "Сейчас включён ускоритель:",
        "current_default_note": (
            "Сейчас используется режим по умолчанию: конкретную видеокарту "
            "выбирает система."
        ),
        "options": "На какой ускоритель переключить?",
        "apply": "Применить",
        "running_warning": (
            "Браузер запущен. Закройте его полностью и нажмите «Проверить снова»"
        ),
        "check_again": "Проверить снова",
        "restore_all": "Вернуть всё назад",
        "restore_browser": "Вернуть настройки этого браузера",
        "pending_section": "Изменённые браузеры",
        "pending_empty": "Нет изменений.",
        "pending_changed": "Изменено: {count}",
        "pending_header_browser": "Браузер",
        "pending_header_option": "Ускоритель",
        "pending_header_when": "Когда",
        "gpu_header_name": "Видеокарта",
        "gpu_header_kind": "Тип",
        "gpu_header_driver": "Драйвер",
        "not_found": "Не найдено",
        "gpu_found": "Найдено: {count}",
        "browsers_summary": "Обнаружено браузеров: {count} — {names}",
        "no_browsers_summary": "Обнаруженные браузеры не найдены.",
        "gpu_integrated": "встроенная",
        "gpu_discrete": "дискретная",
        "gpu_virtual": "виртуальная",
        "gpu_unknown": "неизвестно",
        "platform_mock": "демо-режим",
        "platform": "Платформа: {label}",
        "ready_title": "Все настроено, запустите браузер",
        "ready_detail": "Для браузера «{browser}» выбран ускоритель: {option}.",
        "ready_hint": "Изменение применится после полного перезапуска браузера.",
        "ready_warnings_prefix": "Обратите внимание:",
        "launch": "Запустить браузер",
        "close": "Закрыть",
        "launch_dialog_title": "Запуск браузера",
        "restore_all_title": "Вернуть всё назад",
        "restore_all_confirm": (
            "Вернуть все изменения, сделанные программой, к исходным настройкам?"
        ),
        "restore_browser_title": "Вернуть настройки браузера",
        "restore_browser_confirm": (
            "Вернуть настройки графики для браузера «{browser}» к исходным?"
        ),
        "restore_done_title": "Готово",
        "status_detecting": "Определяем систему, видеокарты и браузеры…",
        "status_detected": "Определение завершено.",
        "status_detected_counts": (
            "Браузеров: {browsers}, видеокарт: {gpus}, вариантов: {options}."
        ),
        "status_detected_problems": (
            "Определение завершено, но часть данных получить не удалось:"
        ),
        "status_checking": "Проверяем, запущен ли браузер…",
        "status_check_running": (
            "Браузер всё ещё запущен. Закройте его полностью и попробуйте снова."
        ),
        "status_check_stopped": "Браузер закрыт. Теперь можно применить настройку.",
        "status_no_browser": "Не выбран браузер.",
        "status_no_option": "Не выбран ускоритель.",
        "status_apply_failed": "Не удалось применить настройку.",
        "status_restore_failed": "Не удалось вернуть настройки.",
        "status_restore_empty": "Изменений не было: возвращать нечего.",
        "status_launch_failed": "Не удалось запустить браузер.",
        "status_applied": "Настройка применена.",
        "status_restored": "Настройки возвращены.",
        "status_restored_names": "Возвращены настройки: {names}.",
        "status_restore_browser": (
            "Настройки браузера «{browser}» возвращены к исходным."
        ),
        "status_no_changes": "Для браузера «{browser}» изменений нет.",
        "status_launched": "Браузер «{browser}» запущен.",
        "hint_select_browser": "Выберите браузер, чтобы применить настройку.",
        "hint_close_browser": "Закройте браузер, чтобы применить настройку.",
        "hint_no_options": "Для выбранного браузера нет доступных вариантов.",
        "status_hint": "F5 — обновить, Esc — закрыть",
        "and_more": "и другое",
        "problem_system": "система",
        "problem_gpus": "видеокарты",
        "problem_browsers": "браузеры",
        "problem_options": "варианты ускорителя",
        "problem_pending": "изменения",
        "problem_notes": "заметки",
        "problem_current": "текущий ускоритель",
        "problem_running": "состояние браузера",
        "problem_pids": "процессы браузера",
        "opt_default": "По умолчанию",
        "opt_default_windows": "По умолчанию — Windows выбирает сам",
        "opt_default_system": "По умолчанию — система выбирает сама",
        "opt_power_saving": "Энергосбережение",
        "opt_high_performance": "Высокая производительность",
        "opt_discrete_nvidia": "Дискретная NVIDIA",
        "opt_discrete_amd": "Дискретная AMD",
        "descr_windows_default": (
            "Windows сам решает, какую видеокарту использовать для браузера."
        ),
        "descr_windows_power": (
            "Встроенная графика: тише и экономичнее, но слабее в играх и 3D."
        ),
        "descr_windows_high": (
            "Дискретная видеокарта: максимальная производительность, "
            "выше расход энергии."
        ),
        "descr_system_auto": (
            "Браузер работает с той видеокартой, которую выберет система."
        ),
        "descr_nvidia_offload": (
            "Запуск через NVIDIA PRIME Render Offload: браузер будет работать "
            "на дискретной видеокарте NVIDIA."
        ),
        "descr_dri_prime": (
            "Запуск через DRI_PRIME=1: браузер будет работать на дискретной "
            "видеокарте AMD (нужны драйверы Mesa)."
        ),
        "descr_nvidia_offload_short": "Запуск через NVIDIA PRIME Render Offload.",
        "descr_dri_prime_short": "Запуск через DRI_PRIME=1.",
        "descr_mock_power": "Встроенная графика: меньше энергопотребление, слабее 3D.",
        "descr_mock_high": "Дискретная видеокарта: быстрее 3D, больше расход батареи.",
        "choice_title": "GPU Switch",
        "choice_hint": (
            "Выберите язык · Choose language · 选择语言 "
            "· Elija su idioma · Sprache wählen"
        ),
        "choice_ok": "Продолжить",
    },
    "en": {
        "subtitle": "Switch the graphics accelerator used by your browser",
        "version_label": "release {version}",
        "system": "System",
        "gpus": "Graphics cards",
        "browser": "Browser",
        "browser_prompt": "Choose a browser found on your PC",
        "current_prefix": "Currently enabled accelerator:",
        "current_default_note": (
            "The default mode is active: the system picks the graphics card."
        ),
        "options": "Which accelerator should be used?",
        "apply": "Apply",
        "running_warning": (
            'The browser is running. Close it completely and click "Check again"'
        ),
        "check_again": "Check again",
        "restore_all": "Restore everything",
        "restore_browser": "Restore this browser's settings",
        "pending_section": "Changed browsers",
        "pending_empty": "No changes.",
        "pending_changed": "Changed: {count}",
        "pending_header_browser": "Browser",
        "pending_header_option": "Accelerator",
        "pending_header_when": "When",
        "gpu_header_name": "Graphics card",
        "gpu_header_kind": "Type",
        "gpu_header_driver": "Driver",
        "not_found": "Not found",
        "gpu_found": "Found: {count}",
        "browsers_summary": "Browsers detected: {count} — {names}",
        "no_browsers_summary": "No browsers were detected.",
        "gpu_integrated": "integrated",
        "gpu_discrete": "discrete",
        "gpu_virtual": "virtual",
        "gpu_unknown": "unknown",
        "platform_mock": "demo mode",
        "platform": "Platform: {label}",
        "ready_title": "All set — start your browser",
        "ready_detail": (
            'Browser "{browser}" now uses the accelerator: {option}.'
        ),
        "ready_hint": (
            "The change takes effect after the browser is fully restarted."
        ),
        "ready_warnings_prefix": "Please note:",
        "launch": "Start browser",
        "close": "Close",
        "launch_dialog_title": "Starting the browser",
        "restore_all_title": "Restore everything",
        "restore_all_confirm": (
            "Restore all changes made by this program to the original settings?"
        ),
        "restore_browser_title": "Restore browser settings",
        "restore_browser_confirm": (
            'Restore the graphics settings of the "{browser}" browser?'
        ),
        "restore_done_title": "Done",
        "status_detecting": "Detecting the system, graphics cards and browsers…",
        "status_detected": "Detection complete.",
        "status_detected_counts": (
            "Browsers: {browsers}, graphics cards: {gpus}, options: {options}."
        ),
        "status_detected_problems": (
            "Detection finished, but some data could not be read:"
        ),
        "status_checking": "Checking whether the browser is running…",
        "status_check_running": (
            "The browser is still running. Close it completely and try again."
        ),
        "status_check_stopped": (
            "The browser is closed. The setting can be applied now."
        ),
        "status_no_browser": "No browser selected.",
        "status_no_option": "No accelerator selected.",
        "status_apply_failed": "Could not apply the setting.",
        "status_restore_failed": "Could not restore the settings.",
        "status_restore_empty": "There was nothing to restore.",
        "status_launch_failed": "Could not start the browser.",
        "status_applied": "The setting has been applied.",
        "status_restored": "The settings have been restored.",
        "status_restored_names": "Restored settings: {names}.",
        "status_restore_browser": 'Settings of the "{browser}" browser are restored.',
        "status_no_changes": 'There are no changes for the "{browser}" browser.',
        "status_launched": 'The "{browser}" browser is starting.',
        "hint_select_browser": "Select a browser to apply the setting.",
        "hint_close_browser": "Close the browser to apply the setting.",
        "hint_no_options": "There are no options for the selected browser.",
        "status_hint": "F5 — refresh, Esc — close",
        "and_more": "and more",
        "problem_system": "system",
        "problem_gpus": "graphics cards",
        "problem_browsers": "browsers",
        "problem_options": "accelerator options",
        "problem_pending": "changes",
        "problem_notes": "notes",
        "problem_current": "current accelerator",
        "problem_running": "browser state",
        "problem_pids": "browser processes",
        "opt_default": "Default",
        "opt_default_windows": "Default — Windows chooses",
        "opt_default_system": "Default — the system chooses",
        "opt_power_saving": "Power saving",
        "opt_high_performance": "High performance",
        "opt_discrete_nvidia": "Discrete NVIDIA",
        "opt_discrete_amd": "Discrete AMD",
        "descr_windows_default": (
            "Windows decides which graphics card the browser should use."
        ),
        "descr_windows_power": (
            "Integrated graphics: quieter and more power-efficient, "
            "but weaker in games and 3D."
        ),
        "descr_windows_high": (
            "Discrete graphics card: maximum performance, higher power draw."
        ),
        "descr_system_auto": (
            "The browser uses whichever graphics card the system picks."
        ),
        "descr_nvidia_offload": (
            "Started with NVIDIA PRIME Render Offload: the browser runs on "
            "the discrete NVIDIA graphics card."
        ),
        "descr_dri_prime": (
            "Started with DRI_PRIME=1: the browser runs on the discrete AMD "
            "graphics card (Mesa drivers are required)."
        ),
        "descr_nvidia_offload_short": "Started with NVIDIA PRIME Render Offload.",
        "descr_dri_prime_short": "Started with DRI_PRIME=1.",
        "descr_mock_power": (
            "Integrated graphics: lower power consumption, weaker 3D."
        ),
        "descr_mock_high": (
            "Discrete graphics card: faster 3D, higher battery drain."
        ),
        "choice_title": "GPU Switch",
        "choice_hint": (
            "Выберите язык · Choose language · 选择语言 "
            "· Elija su idioma · Sprache wählen"
        ),
        "choice_ok": "Continue",
    },
    "zh": {
        "subtitle": "为浏览器切换图形加速器",
        "version_label": "发行版 {version}",
        "system": "系统",
        "gpus": "显卡",
        "browser": "浏览器",
        "browser_prompt": "请选择在您的电脑上发现的浏览器",
        "current_prefix": "当前启用的加速器：",
        "current_default_note": "当前使用默认模式：由系统选择显卡。",
        "options": "切换到哪个加速器？",
        "apply": "应用",
        "running_warning": "浏览器正在运行。请完全关闭后点击“重新检查”",
        "check_again": "重新检查",
        "restore_all": "全部还原",
        "restore_browser": "恢复此浏览器的设置",
        "pending_section": "已更改的浏览器",
        "pending_empty": "没有更改。",
        "pending_changed": "已更改：{count}",
        "pending_header_browser": "浏览器",
        "pending_header_option": "加速器",
        "pending_header_when": "时间",
        "gpu_header_name": "显卡",
        "gpu_header_kind": "类型",
        "gpu_header_driver": "驱动",
        "not_found": "未找到",
        "gpu_found": "找到：{count}",
        "browsers_summary": "检测到的浏览器：{count} — {names}",
        "no_browsers_summary": "未检测到浏览器。",
        "gpu_integrated": "集成",
        "gpu_discrete": "独立",
        "gpu_virtual": "虚拟",
        "gpu_unknown": "未知",
        "platform_mock": "演示模式",
        "platform": "平台：{label}",
        "ready_title": "全部设置完成，请启动浏览器",
        "ready_detail": "已为浏览器“{browser}”选择加速器：{option}。",
        "ready_hint": "该更改将在浏览器完全重启后生效。",
        "ready_warnings_prefix": "请注意：",
        "launch": "启动浏览器",
        "close": "关闭",
        "launch_dialog_title": "正在启动浏览器",
        "restore_all_title": "全部还原",
        "restore_all_confirm": "将本程序所做的所有更改恢复为原始设置？",
        "restore_browser_title": "恢复浏览器设置",
        "restore_browser_confirm": "将“{browser}”浏览器的图形设置恢复为原始状态？",
        "restore_done_title": "完成",
        "status_detecting": "正在检测系统、显卡和浏览器…",
        "status_detected": "检测完成。",
        "status_detected_counts": "浏览器：{browsers}，显卡：{gpus}，选项：{options}。",
        "status_detected_problems": "检测已完成，但部分数据无法获取：",
        "status_checking": "正在检查浏览器是否运行…",
        "status_check_running": "浏览器仍在运行。请完全关闭后重试。",
        "status_check_stopped": "浏览器已关闭。现在可以应用设置。",
        "status_no_browser": "未选择浏览器。",
        "status_no_option": "未选择加速器。",
        "status_apply_failed": "无法应用设置。",
        "status_restore_failed": "无法恢复设置。",
        "status_restore_empty": "没有可恢复的更改。",
        "status_launch_failed": "无法启动浏览器。",
        "status_applied": "设置已应用。",
        "status_restored": "设置已恢复。",
        "status_restored_names": "已恢复设置：{names}。",
        "status_restore_browser": "“{browser}”浏览器的设置已恢复。",
        "status_no_changes": "“{browser}”浏览器没有更改。",
        "status_launched": "正在启动“{browser}”浏览器。",
        "hint_select_browser": "请选择浏览器以应用设置。",
        "hint_close_browser": "请关闭浏览器以应用设置。",
        "hint_no_options": "所选浏览器没有可用的选项。",
        "status_hint": "F5 — 刷新，Esc — 关闭",
        "and_more": "等",
        "problem_system": "系统",
        "problem_gpus": "显卡",
        "problem_browsers": "浏览器",
        "problem_options": "加速器选项",
        "problem_pending": "更改",
        "problem_notes": "备注",
        "problem_current": "当前加速器",
        "problem_running": "浏览器状态",
        "problem_pids": "浏览器进程",
        "opt_default": "默认",
        "opt_default_windows": "默认 — 由 Windows 选择",
        "opt_default_system": "默认 — 由系统选择",
        "opt_power_saving": "节能",
        "opt_high_performance": "高性能",
        "opt_discrete_nvidia": "独立 NVIDIA",
        "opt_discrete_amd": "独立 AMD",
        "descr_windows_default": "Windows 自行决定浏览器使用哪块显卡。",
        "descr_windows_power": "集成显卡：更安静、更省电，但游戏和 3D 性能较弱。",
        "descr_windows_high": "独立显卡：性能最高，但功耗更高。",
        "descr_system_auto": "浏览器使用系统选择的显卡。",
        "descr_nvidia_offload": (
            "通过 NVIDIA PRIME Render Offload 启动：浏览器将运行在独立 "
            "NVIDIA 显卡上。"
        ),
        "descr_dri_prime": (
            "通过 DRI_PRIME=1 启动：浏览器将运行在独立 AMD 显卡上"
            "（需要 Mesa 驱动）。"
        ),
        "descr_nvidia_offload_short": "通过 NVIDIA PRIME Render Offload 启动。",
        "descr_dri_prime_short": "通过 DRI_PRIME=1 启动。",
        "descr_mock_power": "集成显卡：功耗更低，3D 性能较弱。",
        "descr_mock_high": "独立显卡：3D 性能更强，电池消耗更大。",
        "choice_title": "GPU Switch",
        "choice_hint": (
            "Выберите язык · Choose language · 选择语言 "
            "· Elija su idioma · Sprache wählen"
        ),
        "choice_ok": "继续",
    },
    "es": {
        "subtitle": "Cambiar el acelerador gráfico del navegador",
        "version_label": "versión {version}",
        "system": "Sistema",
        "gpus": "Tarjetas gráficas",
        "browser": "Navegador",
        "browser_prompt": "Elija un navegador encontrado en su PC",
        "current_prefix": "Acelerador activado actualmente:",
        "current_default_note": (
            "Se usa el modo predeterminado: el sistema elige la tarjeta gráfica."
        ),
        "options": "¿A qué acelerador cambiar?",
        "apply": "Aplicar",
        "running_warning": (
            "El navegador está en ejecución. Ciérrelo por completo y pulse "
            "«Comprobar de nuevo»"
        ),
        "check_again": "Comprobar de nuevo",
        "restore_all": "Restaurar todo",
        "restore_browser": "Restaurar los ajustes de este navegador",
        "pending_section": "Navegadores modificados",
        "pending_empty": "No hay cambios.",
        "pending_changed": "Modificados: {count}",
        "pending_header_browser": "Navegador",
        "pending_header_option": "Acelerador",
        "pending_header_when": "Cuándo",
        "gpu_header_name": "Tarjeta gráfica",
        "gpu_header_kind": "Tipo",
        "gpu_header_driver": "Controlador",
        "not_found": "No encontrado",
        "gpu_found": "Encontradas: {count}",
        "browsers_summary": "Navegadores detectados: {count} — {names}",
        "no_browsers_summary": "No se detectaron navegadores.",
        "gpu_integrated": "integrada",
        "gpu_discrete": "dedicada",
        "gpu_virtual": "virtual",
        "gpu_unknown": "desconocido",
        "platform_mock": "modo demo",
        "platform": "Plataforma: {label}",
        "ready_title": "Todo listo, inicie el navegador",
        "ready_detail": (
            "Para el navegador «{browser}» se eligió el acelerador: {option}."
        ),
        "ready_hint": (
            "El cambio se aplicará tras reiniciar el navegador por completo."
        ),
        "ready_warnings_prefix": "Atención:",
        "launch": "Iniciar navegador",
        "close": "Cerrar",
        "launch_dialog_title": "Iniciando el navegador",
        "restore_all_title": "Restaurar todo",
        "restore_all_confirm": (
            "¿Restaurar todos los cambios hechos por este programa "
            "a los ajustes originales?"
        ),
        "restore_browser_title": "Restaurar los ajustes del navegador",
        "restore_browser_confirm": (
            "¿Restaurar los ajustes gráficos del navegador «{browser}»?"
        ),
        "restore_done_title": "Listo",
        "status_detecting": (
            "Detectando el sistema, las tarjetas gráficas y los navegadores…"
        ),
        "status_detected": "Detección completada.",
        "status_detected_counts": (
            "Navegadores: {browsers}, tarjetas gráficas: {gpus}, "
            "opciones: {options}."
        ),
        "status_detected_problems": (
            "La detección terminó, pero no se pudieron leer algunos datos:"
        ),
        "status_checking": "Comprobando si el navegador está en ejecución…",
        "status_check_running": (
            "El navegador sigue en ejecución. Ciérrelo por completo e inténtelo "
            "de nuevo."
        ),
        "status_check_stopped": (
            "El navegador está cerrado. Ya se puede aplicar el ajuste."
        ),
        "status_no_browser": "No se ha elegido navegador.",
        "status_no_option": "No se ha elegido acelerador.",
        "status_apply_failed": "No se pudo aplicar el ajuste.",
        "status_restore_failed": "No se pudieron restaurar los ajustes.",
        "status_restore_empty": "No había cambios que restaurar.",
        "status_launch_failed": "No se pudo iniciar el navegador.",
        "status_applied": "El ajuste se ha aplicado.",
        "status_restored": "Los ajustes se han restaurado.",
        "status_restored_names": "Ajustes restaurados: {names}.",
        "status_restore_browser": (
            "Los ajustes del navegador «{browser}» se han restaurado."
        ),
        "status_no_changes": "El navegador «{browser}» no tiene cambios.",
        "status_launched": "Iniciando el navegador «{browser}».",
        "hint_select_browser": "Elija un navegador para aplicar el ajuste.",
        "hint_close_browser": "Cierre el navegador para aplicar el ajuste.",
        "hint_no_options": "No hay opciones para el navegador elegido.",
        "status_hint": "F5 — actualizar, Esc — cerrar",
        "and_more": "y más",
        "problem_system": "sistema",
        "problem_gpus": "tarjetas gráficas",
        "problem_browsers": "navegadores",
        "problem_options": "opciones de acelerador",
        "problem_pending": "cambios",
        "problem_notes": "notas",
        "problem_current": "acelerador actual",
        "problem_running": "estado del navegador",
        "problem_pids": "procesos del navegador",
        "opt_default": "Predeterminado",
        "opt_default_windows": "Predeterminado — Windows elige",
        "opt_default_system": "Predeterminado — lo elige el sistema",
        "opt_power_saving": "Ahorro de energía",
        "opt_high_performance": "Alto rendimiento",
        "opt_discrete_nvidia": "NVIDIA dedicada",
        "opt_discrete_amd": "AMD dedicada",
        "descr_windows_default": (
            "Windows decide qué tarjeta gráfica usa el navegador."
        ),
        "descr_windows_power": (
            "Gráficos integrados: más silenciosos y económicos, "
            "pero más débiles en juegos y 3D."
        ),
        "descr_windows_high": (
            "Tarjeta gráfica dedicada: máximo rendimiento, mayor consumo."
        ),
        "descr_system_auto": (
            "El navegador usa la tarjeta gráfica que elija el sistema."
        ),
        "descr_nvidia_offload": (
            "Inicio con NVIDIA PRIME Render Offload: el navegador se ejecuta "
            "en la tarjeta NVIDIA dedicada."
        ),
        "descr_dri_prime": (
            "Inicio con DRI_PRIME=1: el navegador se ejecuta en la tarjeta AMD "
            "dedicada (se necesitan controladores Mesa)."
        ),
        "descr_nvidia_offload_short": "Inicio con NVIDIA PRIME Render Offload.",
        "descr_dri_prime_short": "Inicio con DRI_PRIME=1.",
        "descr_mock_power": (
            "Gráficos integrados: menor consumo, 3D más débil."
        ),
        "descr_mock_high": (
            "Tarjeta gráfica dedicada: 3D más rápido, más consumo de batería."
        ),
        "choice_title": "GPU Switch",
        "choice_hint": (
            "Выберите язык · Choose language · 选择语言 "
            "· Elija su idioma · Sprache wählen"
        ),
        "choice_ok": "Continuar",
    },
    "de": {
        "subtitle": "Grafikbeschleuniger für den Browser umschalten",
        "version_label": "Release {version}",
        "system": "System",
        "gpus": "Grafikkarten",
        "browser": "Browser",
        "browser_prompt": "Wählen Sie einen auf Ihrem PC gefundenen Browser",
        "current_prefix": "Derzeit aktiver Beschleuniger:",
        "current_default_note": (
            "Es ist der Standardmodus aktiv: Das System wählt die Grafikkarte."
        ),
        "options": "Auf welchen Beschleuniger umschalten?",
        "apply": "Anwenden",
        "running_warning": (
            "Der Browser läuft. Schließen Sie ihn vollständig und klicken Sie "
            "auf „Erneut prüfen“"
        ),
        "check_again": "Erneut prüfen",
        "restore_all": "Alles zurücksetzen",
        "restore_browser": "Einstellungen dieses Browsers zurücksetzen",
        "pending_section": "Geänderte Browser",
        "pending_empty": "Keine Änderungen.",
        "pending_changed": "Geändert: {count}",
        "pending_header_browser": "Browser",
        "pending_header_option": "Beschleuniger",
        "pending_header_when": "Wann",
        "gpu_header_name": "Grafikkarte",
        "gpu_header_kind": "Typ",
        "gpu_header_driver": "Treiber",
        "not_found": "Nicht gefunden",
        "gpu_found": "Gefunden: {count}",
        "browsers_summary": "Gefundene Browser: {count} — {names}",
        "no_browsers_summary": "Es wurden keine Browser gefunden.",
        "gpu_integrated": "integriert",
        "gpu_discrete": "dediziert",
        "gpu_virtual": "virtuell",
        "gpu_unknown": "unbekannt",
        "platform_mock": "Demo-Modus",
        "platform": "Plattform: {label}",
        "ready_title": "Alles eingerichtet, starten Sie den Browser",
        "ready_detail": (
            "Für den Browser „{browser}“ wurde der Beschleuniger gewählt: {option}."
        ),
        "ready_hint": (
            "Die Änderung wird nach einem vollständigen Neustart des Browsers "
            "wirksam."
        ),
        "ready_warnings_prefix": "Bitte beachten:",
        "launch": "Browser starten",
        "close": "Schließen",
        "launch_dialog_title": "Browser wird gestartet",
        "restore_all_title": "Alles zurücksetzen",
        "restore_all_confirm": (
            "Alle von diesem Programm vorgenommenen Änderungen auf die "
            "ursprünglichen Einstellungen zurücksetzen?"
        ),
        "restore_browser_title": "Browser-Einstellungen zurücksetzen",
        "restore_browser_confirm": (
            "Die Grafik-Einstellungen des Browsers „{browser}“ zurücksetzen?"
        ),
        "restore_done_title": "Fertig",
        "status_detecting": (
            "System, Grafikkarten und Browser werden erkannt…"
        ),
        "status_detected": "Erkennung abgeschlossen.",
        "status_detected_counts": (
            "Browser: {browsers}, Grafikkarten: {gpus}, Optionen: {options}."
        ),
        "status_detected_problems": (
            "Die Erkennung ist abgeschlossen, aber einige Daten konnten nicht "
            "gelesen werden:"
        ),
        "status_checking": "Es wird geprüft, ob der Browser läuft…",
        "status_check_running": (
            "Der Browser läuft noch. Schließen Sie ihn vollständig und "
            "versuchen Sie es erneut."
        ),
        "status_check_stopped": (
            "Der Browser ist geschlossen. Die Einstellung kann jetzt "
            "angewendet werden."
        ),
        "status_no_browser": "Kein Browser ausgewählt.",
        "status_no_option": "Kein Beschleuniger ausgewählt.",
        "status_apply_failed": "Die Einstellung konnte nicht angewendet werden.",
        "status_restore_failed": "Die Einstellungen konnten nicht "
        "zurückgesetzt werden.",
        "status_restore_empty": "Es gab nichts zurückzusetzen.",
        "status_launch_failed": "Der Browser konnte nicht gestartet werden.",
        "status_applied": "Die Einstellung wurde angewendet.",
        "status_restored": "Die Einstellungen wurden zurückgesetzt.",
        "status_restored_names": "Zurückgesetzte Einstellungen: {names}.",
        "status_restore_browser": (
            "Die Einstellungen des Browsers „{browser}“ wurden zurückgesetzt."
        ),
        "status_no_changes": (
            "Für den Browser „{browser}“ gibt es keine Änderungen."
        ),
        "status_launched": "Der Browser „{browser}“ wird gestartet.",
        "hint_select_browser": (
            "Wählen Sie einen Browser, um die Einstellung anzuwenden."
        ),
        "hint_close_browser": (
            "Schließen Sie den Browser, um die Einstellung anzuwenden."
        ),
        "hint_no_options": (
            "Für den gewählten Browser gibt es keine Optionen."
        ),
        "status_hint": "F5 — aktualisieren, Esc — schließen",
        "and_more": "und weitere",
        "problem_system": "System",
        "problem_gpus": "Grafikkarten",
        "problem_browsers": "Browser",
        "problem_options": "Beschleuniger-Optionen",
        "problem_pending": "Änderungen",
        "problem_notes": "Hinweise",
        "problem_current": "aktueller Beschleuniger",
        "problem_running": "Browser-Status",
        "problem_pids": "Browser-Prozesse",
        "opt_default": "Standard",
        "opt_default_windows": "Standard — Windows wählt",
        "opt_default_system": "Standard — das System wählt",
        "opt_power_saving": "Energiesparen",
        "opt_high_performance": "Hohe Leistung",
        "opt_discrete_nvidia": "Diskrete NVIDIA",
        "opt_discrete_amd": "Diskrete AMD",
        "descr_windows_default": (
            "Windows entscheidet, welche Grafikkarte der Browser verwendet."
        ),
        "descr_windows_power": (
            "Integrierte Grafik: leiser und sparsamer, aber schwächer "
            "in Spielen und 3D."
        ),
        "descr_windows_high": (
            "Dedizierte Grafikkarte: maximale Leistung, höherer Stromverbrauch."
        ),
        "descr_system_auto": (
            "Der Browser nutzt die Grafikkarte, die das System auswählt."
        ),
        "descr_nvidia_offload": (
            "Start über NVIDIA PRIME Render Offload: Der Browser läuft auf "
            "der dedizierten NVIDIA-Grafikkarte."
        ),
        "descr_dri_prime": (
            "Start über DRI_PRIME=1: Der Browser läuft auf der dedizierten "
            "AMD-Grafikkarte (Mesa-Treiber erforderlich)."
        ),
        "descr_nvidia_offload_short": "Start über NVIDIA PRIME Render Offload.",
        "descr_dri_prime_short": "Start über DRI_PRIME=1.",
        "descr_mock_power": (
            "Integrierte Grafik: geringerer Verbrauch, schwächeres 3D."
        ),
        "descr_mock_high": (
            "Dedizierte Grafikkarte: schnelleres 3D, höherer Akkuverbrauch."
        ),
        "choice_title": "GPU Switch",
        "choice_hint": (
            "Выберите язык · Choose language · 选择语言 "
            "· Elija su idioma · Sprache wählen"
        ),
        "choice_ok": "Weiter",
    },
}

#: Russian option label (or its first segment) -> translation key.
_OPTION_LABEL_EXACT: Dict[str, str] = {
    "По умолчанию — Windows выбирает сам": "opt_default_windows",
    "По умолчанию — система выбирает сама": "opt_default_system",
}

_OPTION_LABEL_PREFIX: Dict[str, str] = {
    "По умолчанию": "opt_default",
    "Энергосбережение": "opt_power_saving",
    "Высокая производительность": "opt_high_performance",
    "Дискретная NVIDIA": "opt_discrete_nvidia",
    "Дискретная AMD": "opt_discrete_amd",
}

#: Russian option description -> translation key.
_OPTION_DESCRIPTION: Dict[str, str] = {
    "Windows сам решает, какую видеокарту использовать для браузера.": (
        "descr_windows_default"
    ),
    "Встроенная графика: тише и экономичнее, но слабее в играх и 3D.": (
        "descr_windows_power"
    ),
    "Дискретная видеокарта: максимальная производительность, выше расход энергии.": (
        "descr_windows_high"
    ),
    "Браузер работает с той видеокартой, которую выберет система.": (
        "descr_system_auto"
    ),
    (
        "Запуск через NVIDIA PRIME Render Offload: браузер будет работать на "
        "дискретной видеокарте NVIDIA."
    ): "descr_nvidia_offload",
    (
        "Запуск через DRI_PRIME=1: браузер будет работать на дискретной "
        "видеокарте AMD (нужны драйверы Mesa)."
    ): "descr_dri_prime",
    "Запуск через NVIDIA PRIME Render Offload.": "descr_nvidia_offload_short",
    "Запуск через DRI_PRIME=1.": "descr_dri_prime_short",
    "Встроенная графика: меньше энергопотребление, слабее 3D.": "descr_mock_power",
    "Дискретная видеокарта: быстрее 3D, больше расход батареи.": "descr_mock_high",
}


def normalize_language(value: Any) -> Optional[str]:
    """Map an arbitrary language tag (``en-US``, ``zh_CN``…) to a supported code."""
    if not value:
        return None
    text = str(value).strip().lower().replace("_", "-")
    if not text:
        return None
    base = text.split("-", 1)[0]
    return base if base in SUPPORTED_LANGUAGES else None


class Translator:
    """Look up strings for one language, falling back to Russian."""

    def __init__(self, language: Optional[str] = None) -> None:
        code = normalize_language(language) or DEFAULT_LANGUAGE
        self.language = code
        self._table = TRANSLATIONS[code]
        self._fallback = TRANSLATIONS[DEFAULT_LANGUAGE]

    def t(self, key: str, **values: Any) -> str:
        template = self._table.get(key)
        if template is None:
            template = self._fallback.get(key, key)
        if not values:
            return template
        try:
            return template.format(**values)
        except (KeyError, IndexError, ValueError):
            return template


def language_name(code: str) -> str:
    for value, name in LANGUAGES:
        if value == code:
            return name
    return code


def _guess_system_language() -> str:
    try:
        tag = locale.getlocale()[0] or locale.getdefaultlocale()[0]
    except Exception:
        tag = None
    return normalize_language(tag) or DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# Saved choice (settings.json in the per-user data directory)
# ---------------------------------------------------------------------------


def _settings_path() -> Path:
    return Path(default_data_dir()) / SETTINGS_FILE_NAME


def load_saved_language() -> Optional[str]:
    """Return the language saved by an earlier run, or None when unavailable."""
    try:
        data = json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return normalize_language(data.get("language"))


def save_language(code: str) -> None:
    """Persist the chosen language; silently ignores read-only environments."""
    normalized = normalize_language(code) or DEFAULT_LANGUAGE
    try:
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"language": normalized}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


def initial_language() -> str:
    """Language for a normal startup: saved choice, then the system locale."""
    return load_saved_language() or _guess_system_language()


# ---------------------------------------------------------------------------
# Backend-provided option text (labels and descriptions are always Russian)
# ---------------------------------------------------------------------------


def translate_option_label(label: str, translator: Translator) -> str:
    """Translate a backend option label for a non-Russian interface."""
    text = str(label or "")
    if translator.language == DEFAULT_LANGUAGE or not text:
        return text
    exact = _OPTION_LABEL_EXACT.get(text)
    if exact is not None:
        return translator.t(exact)
    if " — " in text:
        head, tail = text.split(" — ", 1)
        key = _OPTION_LABEL_PREFIX.get(head.strip())
        if key is not None:
            return translator.t(key) + " — " + tail
    return text


def translate_option_description(description: str, translator: Translator) -> str:
    """Translate a backend option description for a non-Russian interface."""
    text = str(description or "")
    if translator.language == DEFAULT_LANGUAGE or not text:
        return text
    key = _OPTION_DESCRIPTION.get(text)
    return translator.t(key) if key is not None else text


def ask_language(root: Any, initial: Optional[str] = None) -> Optional[str]:
    """Ask which interface language to use on the very first launch.

    Returns the chosen code, or ``None`` when the dialog was closed without a
    choice (the caller then keeps the system language).  The answer is stored
    by the caller through :func:`save_language`; later changes happen in the
    header of the main window and need no dialog at all.
    """
    try:
        import tkinter as tk
        from tkinter import ttk

        from app import theme as theme_module
    except Exception:
        return None

    start = normalize_language(initial) or DEFAULT_LANGUAGE
    translated = Translator(start)
    try:
        theme = theme_module.apply(root)
        page = theme.colors["page"]
        card = theme.colors["card"]
        text = theme.colors["text"]
        text2 = theme.colors["text2"]
        font_title = theme.font(20, "bold")
        font_body = theme.font(14)
        px = theme.px
    except Exception:
        theme = None
        page, card, text, text2 = "#F3F3F3", "#FFFFFF", "#1A1A1A", "#5C5C5C"
        font_title = ("Segoe UI", -20, "bold")
        font_body = ("Segoe UI", -14)
        px = lambda value: max(1, int(round(value)))

    chosen: List[str] = []
    dialog = tk.Toplevel(root)
    dialog.title("GPU Switch")
    dialog.transient(root)
    dialog.resizable(False, False)
    try:
        dialog.configure(background=page)
    except Exception:
        pass

    outer = tk.Frame(dialog, background=page, padx=px(24), pady=px(20))
    outer.grid(row=0, column=0, sticky="nsew")
    outer.columnconfigure(0, weight=1)

    tk.Label(
        outer,
        text=translated.t("choice_title"),
        background=page,
        foreground=text,
        font=font_title,
        anchor="w",
        justify="left",
    ).grid(row=0, column=0, sticky="w")
    tk.Label(
        outer,
        text=translated.t("choice_hint"),
        background=page,
        foreground=text2,
        font=font_body,
        anchor="w",
        justify="left",
        wraplength=px(360),
    ).grid(row=1, column=0, sticky="w", pady=(px(6), px(12)))

    options = tk.Frame(outer, background=card, padx=px(14), pady=px(10))
    options.grid(row=2, column=0, sticky="ew")
    options.columnconfigure(0, weight=1)
    variable = tk.StringVar(master=dialog, value=start)
    for offset, (code, name) in enumerate(LANGUAGES):
        ttk.Radiobutton(
            options,
            text=name,
            value=code,
            variable=variable,
            style="Option.TRadiobutton",
        ).grid(row=offset, column=0, sticky="w", pady=(px(2), 0))

    buttons = tk.Frame(outer, background=page)
    buttons.grid(row=3, column=0, sticky="e", pady=(px(16), 0))

    def finish() -> None:
        try:
            chosen.append(str(variable.get() or start))
        finally:
            dialog.destroy()

    def cancel(_event: Any = None) -> None:
        dialog.destroy()

    ttk.Button(
        buttons, text=translated.t("choice_ok"), style="Accent.TButton", command=finish
    ).grid(row=0, column=0)
    dialog.bind("<Return>", lambda _event: finish())
    dialog.bind("<Escape>", cancel)
    dialog.protocol("WM_DELETE_WINDOW", cancel)

    dialog.update_idletasks()
    try:
        width = max(dialog.winfo_reqwidth(), px(420))
        height = dialog.winfo_reqheight()
        screen_w = dialog.winfo_screenwidth()
        screen_h = dialog.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.grab_set()
        dialog.focus_force()
    except Exception:
        pass
    try:
        root.wait_window(dialog)
    except Exception:
        return None
    if not chosen:
        return None
    return normalize_language(chosen[0]) or DEFAULT_LANGUAGE
