# GPU Switch

**Sprache:** [Русский](README.md) · [English](README.en.md) · [中文](README.zh.md) · [Español](README.es.md) · [Deutsch](README.de.md)

Eine kleine Desktop-Anwendung für Windows und Linux, die den Grafikbeschleuniger (die Grafikkarte) für den ausgewählten Browser umschaltet. Alles läuft im Kontext des aktuellen Benutzers — Administratorrechte sind nicht erforderlich. Die Oberfläche ist im Windows-11-Stil gestaltet: Karten mit feiner Umrandung, Segoe UI Variable, systemweite Akzentfarbe.

```
Windows 10/11 · Linux · Python 3.9+ · Tkinter · без сторонних библиотек
Установщик BrouserGPUSwitch-Setup.exe, один файл BrouserGPUSwitch.exe
и архив для Linux собираются build_exe.bat / build_linux.sh
```

## Wozu das gut ist

Auf Notebooks und PCs mit zwei Grafikkarten (integrierte Intel-/AMD-Grafik und dedizierte NVIDIA-/AMD-Grafikkarte) kann der Browser standardmäßig auf der schwachen integrierten Grafik laufen. Mit GPU Switch lässt sich für Chrome, Edge, Firefox, Yandex Browser und andere Browser die erzwungene Nutzung der dedizierten Grafikkarte auswählen — und ebenso einfach wieder rückgängig machen.

## Funktionen

1. Erkennt das Betriebssystem (Windows 10/11 oder Linux), seine Version und Architektur.
2. Findet installierte Browser (Registrierungsschlüssel StartMenuInternet und bekannte Pfade unter Windows; .desktop-Dateien unter Linux).
3. Erkennt Grafikchips: integrierte, dedizierte und virtuelle.
4. Zeigt ein Auswahlfenster: „Wählen Sie einen auf Ihrem PC gefundenen Browser“.
5. Trägt in die Liste der Beschleuniger die Option ein, die aktuell für den Browser gilt: Sie ist als ausgewählt markiert.
6. Ermöglicht die Auswahl, auf welchen Beschleuniger umgeschaltet werden soll.
7. Fordert zum Schließen des Browsers auf und prüft anhand der Prozesse, dass er wirklich geschlossen ist.
8. Ändert die Einstellungen im System — nur für den aktuellen Benutzer.
9. Zeigt nach dem Umschalten das Fenster „Alles eingerichtet, starten Sie den Browser“ mit einer Schaltfläche zum Starten dieses Browsers.
10. Die jederzeit verfügbare Schaltfläche „Alles zurücksetzen“ macht alle vom Programm vorgenommenen Änderungen rückgängig.

## So sieht es aus

![Hauptfenster von GPU Switch](docs/gui-main.png)

*Hauptfenster: die Karten „System“, „Grafikkarten“, „Browser“, die Auswahl des Beschleunigers und die unten fixierte Akzent-Schaltfläche „Anwenden“.*

![Fenster nach dem Anwenden der Einstellung](docs/gui-success.png)

*Nach dem Umschalten: „Alles eingerichtet, starten Sie den Browser“ mit einer Schaltfläche zum Starten des Browsers.*

## Sprachen

Die Oberfläche ist in fünf Sprachen übersetzt: **Russisch**, **Englisch**, **Chinesisch**, **Spanisch**, **Deutsch**.

Die Sprache wird in der Liste oben rechts im Hauptfenster ausgewählt — neben der Versionsnummer. Beim ersten Start wird die Systemsprache (oder die zuvor gespeicherte) verwendet. Nach der Auswahl startet das Fenster sofort in der neuen Sprache neu, und die Auswahl wird in `settings.json` neben den Programmdaten gespeichert (siehe „Wo die Daten gespeichert werden“) und bei den folgenden Starts verwendet.

Übersetzt werden nur die Elemente der Programmoberfläche. Die Namen von Grafikkarten und Browsern sowie Versionsnummern sind Systemdaten und bleiben unverändert. Die Kommandozeilenmodi (`--self-test`, `--diagnostics`) geben ihren Bericht immer auf Russisch aus.

## Voraussetzungen

* Windows 10 (1803 oder neuer) oder Windows 11 bzw. Linux mit X11/Wayland.
* Python 3.9+ mit Tkinter.
  * Windows: [python.org](https://www.python.org/downloads/) — Tkinter ist im Installer enthalten.
  * Debian/Ubuntu: `sudo apt install python3-tk`
  * Fedora: `sudo dnf install python3-tkinter`
  * Arch: `sudo pacman -S tk`
* Es werden keine Python-Pakete von Drittanbietern benötigt.
* Für die fertige `BrouserGPUSwitch.exe` sind Python und Tkinter nicht erforderlich — siehe „Fertiger Installer und Builds“.

## Start

Windows:

```bat
run.bat
```

oder über die Eingabeaufforderung:

```bat
py -3 main.py
```

Linux:

```sh
chmod +x run.sh
./run.sh
```

oder:

```sh
python3 main.py
```

Demomodus (ändert nichts auf dem Computer, zeigt Demodaten):

```
python main.py --mock
```

## Fertiger Installer und Builds (Python nicht erforderlich)

Selbst erstellen (einmalig ist eine Internetverbindung nötig — für die Installation von PyInstaller):

```bat
build_exe.bat
```

Das Skript prüft Python 3.9+, installiert bei Bedarf PyInstaller und erstellt drei Varianten:

* `dist\BrouserGPUSwitch-Setup.exe` — der Installer. Er bietet die Wahl des Installationsordners, installiert das Programm in `%LOCALAPPDATA%\Programs\BrouserGPUSwitch` (Administratorrechte nicht erforderlich), legt Verknüpfungen im Startmenü und auf Wunsch auf dem Desktop an, fügt „GPU Switch deinstallieren“ und einen Eintrag in der Liste der installierten Windows-Programme hinzu;
* `dist\BrouserGPUSwitch.exe` — eine einzelne Datei, etwa 11–12 MB, wird wie eine normale exe kopiert und weitergegeben;
* `dist\BrouserGPUSwitch\BrouserGPUSwitch.exe` — ein Ordner mit den zugehörigen Dateien daneben: Es muss nichts entpackt werden, daher startet er auch dort, wo die Ein-Datei-Variante blockiert wird.

Der Installer enthält den Ordner `dist\BrouserGPUSwitch`, daher muss er nach diesem erstellt werden — `build_exe.bat` erledigt das selbst. Alle Varianten durchlaufen am Ende der Erstellung eine Selbstprüfung, der Installer zusätzlich eine Testinstallation im stillen Modus.

Für Linux gibt es im Projekt `build_linux.sh`: Es erstellt `dist/BrouserGPUSwitch-linux-x86_64.tar.gz` — ein Archiv mit dem Programmordner, `install.sh`, `uninstall.sh` und einer `.desktop`-Verknüpfung. Der Benutzer entpackt das Archiv und führt `./install.sh` aus; das Programm wird in `~/.local` installiert, root ist nicht erforderlich:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

Wenn das Projekt auf GitHub liegt, wird all das automatisch erstellt: Tab **Actions** → **build** → **Run workflow**. Die fertigen Installer, die Ein-Datei-Variante, das Ordner-Archiv und das Linux-Archiv erscheinen in den angehängten Dateien des Laufs (Artifact). Beim Pushen eines Tags wie `v1.0.0` werden sie an das Release angehängt — so lassen sie sich per Link an Benutzer weitergeben.

Verhalten der erstellten Datei:

* beim Doppelklick öffnet sich nur das Programmfenster — **es gibt überhaupt kein Konsolenfenster**: Die exe ist als Fensteranwendung erstellt, daher erscheint nicht einmal kurz ein schwarzes Rechteck;
* Administratorrechte sind nicht nötig: Im Manifest der exe steht `asInvoker`, alle Änderungen werden im Profil des aktuellen Benutzers geschrieben (`HKCU` unter Windows, `~/.config` und `~/.local/share` unter Linux). Wenn Windows eine Administratorabfrage anzeigt, stammt sie nicht vom Programm, sondern von der Shell bzw. vom Antivirusprogramm; starten Sie die exe aus einem normalen Benutzerordner, nicht aus `C:\Program Files`;
* beim ersten Start wird die Systemsprache übernommen, geändert werden kann sie in der Liste oben rechts im Fenster;
* der Installer installiert das Programm ohne Administratorrechte in `%LOCALAPPDATA%\Programs\BrouserGPUSwitch`, legt Verknüpfungen im Startmenü, den Eintrag „GPU Switch deinstallieren“ und einen Eintrag in der Liste der installierten Programme an; eine Desktop-Verknüpfung ist optional;
* in den Kommandozeilenmodi (`BrouserGPUSwitch.exe --self-test`, `BrouserGPUSwitch.exe --diagnostics`) verbindet sich das Programm mit der Konsole, aus der es gestartet wurde, und gibt den Bericht dort aus. Die Shell wartet nicht auf eine Fensteranwendung, daher kann die Eingabeaufforderung früher zurückkehren als der Bericht; falls das stört, leiten Sie die Ausgabe in eine Datei um: `BrouserGPUSwitch.exe --diagnostics > report.txt`;
* Einstellungen und Zurücksetzen funktionieren wie gewohnt, die Daten liegen in `%APPDATA%\BrowserGpuSwitch\`;
* die exe und der Installer werden unter Windows erstellt. Unter Linux erzeugt PyInstaller eine ausführbare Datei ohne Erweiterung, sie muss unter Linux erstellt werden — dafür gibt es `build_linux.sh`.

### Wenn das Programm nicht startet

**„Windows hat Ihren PC geschützt“** (SmartScreen) — das ist kein Fehler des Programms. Die Datei ist nicht mit einem kostenpflichtigen Zertifikat signiert, daher warnt Windows vor einem unbekannten Herausgeber. Klicken Sie auf „Weitere Informationen“ → „Trotzdem ausführen“. Für eine öffentliche Verbreitung ohne diese Warnung ist eine Codesignatur erforderlich.

**„Error. Could not create temporary directory!“** — so verhält sich die Ein-Datei-Variante, wenn das System oder ein Antivirusprogramm das Entpacken in ein temporäres Verzeichnis verhindert. In dieser Version entpackt sich die Ein-Datei-Variante nicht nach `%TEMP%`, sondern nach `%LOCALAPPDATA%`, daher sollte der Fehler verschwinden. Falls die Einschränkung dennoch greift, verwenden Sie den Installer `BrouserGPUSwitch-Setup.exe` oder den Ordner `dist\BrouserGPUSwitch\BrouserGPUSwitch.exe` — beide entpacken nichts. Den Ordner können Sie auch manuell erstellen:

```bat
python -m PyInstaller --noconfirm --clean packaging\gpu-switch.spec
```

Wenn Sie den Ordner auf einen anderen Computer übertragen, kopieren Sie ihn vollständig — die exe startet ohne die zugehörigen Dateien daneben nicht. Der Installer `BrouserGPUSwitch-Setup.exe` lässt sich als einzelne Datei übertragen: Er enthält den Ordner in sich. Das Flag `--silent` installiert das Programm ohne Rückfragen (zum Beispiel `BrouserGPUSwitch-Setup.exe --silent --target=D:\Apps\GPUSwitch`).

## Bedienung

1. Starten Sie das Programm; die Sprache der Oberfläche lässt sich sofort in der Liste oben rechts im Fenster ändern. Warten Sie, bis die Erkennung von System, Browsern und Grafikkarten abgeschlossen ist.
2. Wählen Sie im Block „Wählen Sie einen auf Ihrem PC gefundenen Browser“ einen Browser.
3. Im Block „Auf welchen Beschleuniger umschalten?“ ist bereits die aktuell gültige Option markiert.
4. Wählen Sie im Block „Auf welchen Beschleuniger umschalten?“ die gewünschte Option.
5. Wenn der Browser läuft, fordert das Programm Sie auf, ihn vollständig zu schließen und auf „Erneut prüfen“ zu klicken. Die Schaltfläche „Anwenden“ wird erst verfügbar, wenn die Browserprozesse beendet sind.
6. Klicken Sie auf „Anwenden“. Es erscheint das Fenster „Alles eingerichtet, starten Sie den Browser“ mit der Schaltfläche „Browser starten“.
7. Um die Änderungen rückgängig zu machen, klicken Sie auf „Alles zurücksetzen“ und bestätigen Sie den Vorgang.

## Was genau im System geändert wird

### Windows

Verwendet wird die Windows-Benutzereinstellung „Grafikeinstellungen“:

```
HKCU\Software\Microsoft\DirectX\UserGpuPreferences
```

* Der Name des Werts ist der vollständige Pfad zur exe-Datei des Browsers, zum Beispiel `C:\Program Files\Google\Chrome\Application\chrome.exe`.
* Die Daten des Werts sind eine Zeichenkette der Form `GpuPreference=2;`, wobei `0` für Standard, `1` für Energieeinsparung (integrierte Grafik) und `2` für hohe Leistung (dedizierte Grafik) steht.
* Die übrigen Felder der Zeichenkette (falls vorhanden) bleiben erhalten.
* Beim Zurücksetzen wird nur das entfernt, was das Programm erstellt hat; wenn der Wert bereits vorher existierte, wird der ursprüngliche Inhalt wiederhergestellt.

Die Änderung wird nach einem vollständigen Neustart des Browsers wirksam. Diese Funktion wird ab Windows 10 1803 unterstützt und funktioniert für Anwendungen, die die GPU-Auswahl des Systems nutzen (Chromium-Browser, Firefox und die meisten Spiele).

### Linux

Für jeden Browser wird ein eigener Start erstellt:

* ein Wrapper-Skript im Datenverzeichnis des Programms (`~/.config/browser-gpu-switch/wrappers/`);
* eine überschriebene `.desktop`-Datei in `~/.local/share/applications/` mit der Markierung `X-BrowserGpuSwitch-Mode`.

Der Wrapper setzt Umgebungsvariablen und startet den ursprünglichen Browser:

* für NVIDIA PRIME Render Offload:
  ```
  __NV_PRIME_RENDER_OFFLOAD=1
  __GLX_VENDOR_LIBRARY_NAME=nvidia
  __VK_LAYER_NV_optimus=NVIDIA_only
  ```
* für DRI_PRIME (AMD/Intel):
  ```
  DRI_PRIME=1
  ```

Beim Zurücksetzen werden nur der vom Programm erstellte Wrapper und die `.desktop`-Datei entfernt. Fremde Überschreibungen bleiben unberührt: Wenn für den Browser bereits eine `.desktop`-Datei eines Drittanbieters existiert, weigert sich das Programm, sie zu überschreiben, und teilt dies mit.

## Wo die Daten gespeichert werden

* Windows: `%APPDATA%\BrowserGpuSwitch\`
* Linux: `~/.config/browser-gpu-switch/`
* Verzeichnis überschreiben: Umgebungsvariable `BROWSER_GPU_SWITCH_HOME`.

Im Verzeichnis befinden sich:

* `state.json` — Angaben zu den angewendeten Einstellungen (werden zum Zurücksetzen benötigt, auch nach einem Neustart des Programms);
* `settings.json` — die gewählte Sprache der Oberfläche (wird nach der ersten Sprachauswahl erstellt);
* `backups/` — Sicherungskopien der geänderten Dateien (Linux).

Wenn Sie das Verzeichnis von Hand löschen, kann das Programm die Änderungen nicht mehr zurücksetzen — verwenden Sie zuerst „Alles zurücksetzen“.

## Kommandozeile

```
python main.py                     # обычный запуск
python main.py --mock              # демо-режим, ничего не меняет
python main.py --self-test         # самопроверка без окна, код возврата 0/1
python main.py --diagnostics       # технический отчёт: ОС, GPU, браузеры, процессы, откат
python main.py --ui-smoke-test     # скрытая проверка интерфейса
python main.py --screenshot-mode   # окно для скриншота (демо-данные)
python main.py --platform windows  # принудительно выбрать бэкенд
```

Die erstellte `BrouserGPUSwitch.exe` unterstützt dieselben Optionen: `BrouserGPUSwitch.exe --self-test`, `BrouserGPUSwitch.exe --diagnostics`, `BrouserGPUSwitch.exe --mock` und die übrigen. Der Bericht wird in die Konsole ausgegeben, aus der die exe gestartet wurde; zum Speichern in eine Datei: `BrouserGPUSwitch.exe --diagnostics > report.txt`.

## Einschränkungen und Hinweise

* Die Einstellung gilt nur für den aktuellen Benutzer. Andere Benutzerkonten sind nicht betroffen.
* Windows: Einige Programme ignorieren die systemweite GPU-Einstellung und wählen den Adapter selbst. Das ist eine Einschränkung von Windows, nicht des Programms.
* Linux: Das Umschalten funktioniert für den Start über eine `.desktop`-Datei (Anwendungsmenü, Dock). Ein Start aus dem Terminal unter Umgehung der `.desktop`-Datei verwendet die Standardeinstellungen.
* Linux + Wayland: Das Verhalten hängt vom Compositor und vom Treiber ab; in manchen Umgebungen ist eine erneute Anmeldung an der Sitzung erforderlich.
* Flatpak-/Snap-Versionen von Browsern können Umgebungsvariablen aufgrund der Sandbox ignorieren.
* NVIDIA PRIME Render Offload erfordert den installierten proprietären NVIDIA-Treiber.
* „Standard“ wählt keine bestimmte Grafikkarte — die Entscheidung bleibt beim Betriebssystem.
* Das Programm installiert keine Treiber und erfordert keinen Neustart.
* Die erstellte `.exe` ist nicht mit einem Zertifikat signiert: SmartScreen kann die Warnung „Windows hat Ihren PC geschützt“ anzeigen („Weitere Informationen“ → „Trotzdem ausführen“), und Antivirenprogramme schlagen bei PyInstaller-Builds manchmal fälschlicherweise an. Für eine öffentliche Verbreitung ohne Warnungen ist eine Codesignatur erforderlich.
* Die Ein-Datei-Variante entpackt sich bei jedem Start, aber nicht nach `%TEMP%`, sondern nach `%LOCALAPPDATA%`. Wenn das System oder ein Antivirusprogramm auch das verhindert, verwenden Sie den Installer `BrouserGPUSwitch-Setup.exe` oder den Ordner `dist\BrouserGPUSwitch\` — sie entpacken nichts. Alle Builds erstellt `build_exe.bat`, unter Linux `build_linux.sh`.
* Administratorrechte sind weder zum Starten noch für den Betrieb erforderlich. Das Programm ändert nur die Einstellungen des aktuellen Benutzers.

## Diagnose

Wenn der Browser nicht gefunden wird oder das Umschalten nicht funktioniert:

```
python main.py --diagnostics
```

Der Bericht enthält das Betriebssystem, die Liste der GPUs, gefundene Browser mit Pfaden, laufende Prozesse, verfügbare Umschaltoptionen, angewendete Änderungen und technische Informationen des Backends. Selbstprüfung:

```
python main.py --self-test
```

## Entwicklung

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

Das Erscheinungsbild ist in `app/theme.py` ausgelagert: Dort befinden sich die Windows-11-Palette (`#F3F3F3` / weiße Karten / Akzent `#0067C0`), der Schrift-Stack `Segoe UI Variable Text → Segoe UI → …`, die Abstandsskala und alle ttk-Stile (Karten, Schaltflächen, Combobox, Radiobuttons, Tabellen). Die Größen werden anhand des tatsächlichen DPI neu berechnet; in `app/main.py` wird vor dem Erstellen des Fensters DPI-Awareness aktiviert, damit der Text bei 125–150 % scharf bleibt. Neue Stile fügen Sie dort hinzu, nicht in `app/ui.py`.

Tests:

```
python -m unittest discover -s tests -v
```

exe direkt erstellen, ohne bat-Datei:

```
python -m pip install --upgrade "pyinstaller>=6.0"
python -m PyInstaller --noconfirm --clean packaging/gpu-switch.spec
```

Das Skript `build_exe.bat` erledigt dasselbe plus eine Selbstprüfung des Ergebnisses. Eigenes Symbol für die exe: Legen Sie `packaging/gpu-switch.ico` ab — die Spec übernimmt es automatisch.

Syntaxprüfung:

```
python -m compileall app
```

Die Tests ändern keine realen Einstellungen: Das Windows-Backend wird mit einer nachgebildeten Registrierung und einer nachgebildeten Prozessliste getestet, das Linux-Backend mit nachgebildeten sysfs-/proc-Verzeichnissen und einem temporären Home-Verzeichnis.

### Unabhängige Prüfung

Ergebnisse der QA-Prüfung, die Nachverfolgung aller zehn Anforderungen, die Testabdeckung und eine ehrliche Liste der Einschränkungen: [docs/qa-report.md](docs/qa-report.md).

Ergebnis: 236 Tests OK (1 umgebungsbedingt übersprungen), 44 Integrationstests, keine funktionalen Defekte gefunden. Ein echter Schreibzugriff auf die Windows-Registrierung und die Prüfung laufender Prozesse lassen sich in der Sandbox nicht testen — die Logik wurde mit nachgebildeter Registrierung und Prozessliste geprüft; auf einem normalen Rechner empfiehlt sich ein Kontrollstart.

## Version

1.0.0
