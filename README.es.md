# GPU Switch

**Idioma:** [Русский](README.md) · [English](README.en.md) · [中文](README.zh.md) · [Español](README.es.md) · [Deutsch](README.de.md)

Una pequeña aplicación de escritorio para Windows y Linux que cambia el acelerador gráfico (la tarjeta gráfica) del navegador seleccionado. Todo funciona dentro del usuario actual: no hacen falta permisos de administrador. La interfaz sigue el estilo de Windows 11: tarjetas con borde fino, Segoe UI Variable y el color de acento del sistema.

```
Windows 10/11 · Linux · Python 3.9+ · Tkinter · без сторонних библиотек
Установщик BrouserGPUSwitch-Setup.exe, один файл BrouserGPUSwitch.exe
и архив для Linux собираются build_exe.bat / build_linux.sh
```

## Para qué sirve

En portátiles y equipos con dos tarjetas gráficas (una integrada Intel/AMD y otra dedicada NVIDIA/AMD), el navegador puede usar por defecto la gráfica integrada, que es la más lenta. GPU Switch permite forzar el uso de la tarjeta dedicada en Chrome, Edge, Firefox, Yandex Browser y otros navegadores, y revertir el cambio con la misma facilidad.

## Qué hace

1. Detecta el sistema operativo (Windows 10/11 o Linux), su versión y su arquitectura.
2. Encuentra los navegadores instalados (el registro StartMenuInternet y las rutas conocidas en Windows; los archivos .desktop en Linux).
3. Identifica los chips gráficos: integrados, dedicados y virtuales.
4. Muestra una ventana de selección: «Seleccione un navegador de los detectados en su PC».
5. Preselecciona en la lista de aceleradores la opción que el navegador está usando ahora mismo: aparece marcada como seleccionada.
6. Permite elegir a qué acelerador cambiar.
7. Pide cerrar el navegador y comprueba que de verdad está cerrado (por sus procesos).
8. Cambia la configuración del sistema, solo para el usuario actual.
9. Después del cambio muestra la ventana «Todo listo, inicie el navegador», con un botón para abrir ese navegador.
10. El botón «Revertir todo», siempre disponible, deshace todos los cambios que ha hecho la aplicación.

## Cómo se ve

![Ventana principal de GPU Switch](docs/gui-main.png)

*Ventana principal: las tarjetas «Sistema», «Tarjetas gráficas» y «Navegador», la selección del acelerador y, fijado abajo, el botón de acento «Aplicar».*

![Ventana después de aplicar la configuración](docs/gui-success.png)

*Después de cambiar la configuración: «Todo listo, inicie el navegador», con un botón para abrir el navegador.*

## Idiomas

La interfaz está traducida a cinco idiomas: **ruso**, **inglés**, **chino**, **español** y **alemán**.

El idioma se elige en la lista de la esquina superior derecha de la ventana principal, junto al número de versión. En el primer inicio se usa el idioma del sistema (o el que se haya guardado antes). Al elegirlo, la ventana se reinicia de inmediato en el nuevo idioma, y la elección se guarda en `settings.json`, junto a los datos del programa (véase «Dónde se guardan los datos»), y se usa en los siguientes inicios.

Solo se traducen los elementos de la interfaz del programa. Los nombres de las tarjetas gráficas y de los navegadores, y las versiones, son datos del sistema y se quedan tal cual. Los modos de servicio de la línea de comandos (`--self-test`, `--diagnostics`) siempre imprimen el informe en ruso.

## Requisitos

* Windows 10 (1803 o posterior) o Windows 11, o Linux con X11/Wayland.
* Python 3.9+ con Tkinter.
  * Windows: [python.org](https://www.python.org/downloads/) — Tkinter viene incluido en el instalador.
  * Debian/Ubuntu: `sudo apt install python3-tk`
  * Fedora: `sudo dnf install python3-tkinter`
  * Arch: `sudo pacman -S tk`
* No se necesita ningún paquete de Python de terceros.
* Para el `BrouserGPUSwitch.exe` ya compilado no hacen falta Python ni Tkinter; véase «Instalador y compilaciones listos».

## Ejecución

Windows:

```bat
run.bat
```

o desde la línea de comandos:

```bat
py -3 main.py
```

Linux:

```sh
chmod +x run.sh
./run.sh
```

o:

```sh
python3 main.py
```

Modo de demostración (no cambia nada en el equipo y muestra datos de ejemplo):

```
python main.py --mock
```

## Instalador y compilaciones listos (sin Python)

Compilarlo uno mismo (solo hace falta internet la primera vez, para instalar PyInstaller):

```bat
build_exe.bat
```

El script comprueba que haya Python 3.9+, instala PyInstaller si hace falta y compila tres variantes:

* `dist\BrouserGPUSwitch-Setup.exe`: el instalador. Propone una carpeta de instalación, instala el programa en `%LOCALAPPDATA%\Programs\BrouserGPUSwitch` (no hacen falta permisos de administrador), crea accesos directos en el menú Inicio y, si se quiere, en el escritorio, añade «Desinstalar GPU Switch» y una entrada en la lista de programas instalados de Windows;
* `dist\BrouserGPUSwitch.exe`: un único archivo de unos 11–12 MB, que se copia y se mueve como un exe normal;
* `dist\BrouserGPUSwitch\BrouserGPUSwitch.exe`: una carpeta con los archivos auxiliares al lado; no hay que descomprimir nada, por eso arranca incluso allí donde la compilación de un solo archivo queda bloqueada.

El instalador lleva dentro la carpeta `dist\BrouserGPUSwitch`, así que hay que compilarlo después de ella: `build_exe.bat` lo hace solo. Todas las variantes pasan la autocomprobación al final de la compilación, y el instalador además una instalación silenciosa de prueba.

Para Linux, el proyecto incluye `build_linux.sh`: compila `dist/BrouserGPUSwitch-linux-x86_64.tar.gz`, un archivo con la carpeta del programa, `install.sh`, `uninstall.sh` y un acceso directo `.desktop`. El usuario descomprime el archivo y ejecuta `./install.sh`; el programa se instala en `~/.local` y no hace falta root:

```bash
chmod +x build_linux.sh
./build_linux.sh
```

Si el proyecto está en GitHub, lo mismo se compila de forma automática: pestaña **Actions** → **build-exe** → **Run workflow**; los archivos generados aparecerán en los archivos adjuntos de la ejecución (artifact). Al enviar una etiqueta como `v1.0.0`, el exe y el zip se adjuntan a la release, de modo que se pueden dar a los usuarios con un enlace.

Cómo se comporta el archivo compilado:

* al hacer doble clic solo se abre la ventana del programa: **no hay ninguna ventana de consola**, porque el exe está compilado como aplicación de ventana y no parpadea ni un rectángulo negro;
* no hacen falta permisos de administrador: el manifiesto del exe declara `asInvoker`, y todos los cambios se escriben en el perfil del usuario actual (`HKCU` en Windows, `~/.config` y `~/.local/share` en Linux). Si Windows muestra una petición de permisos de administrador, no es la aplicación sino el intérprete o el antivirus; ejecute el exe desde una carpeta de usuario normal, no desde `C:\Program Files`;
* en el primer inicio se usa el idioma del sistema, y se puede cambiar en la lista de la esquina superior derecha de la ventana;
* en los modos de línea de comandos (`BrouserGPUSwitch.exe --self-test`, `BrouserGPUSwitch.exe --diagnostics`) el programa se conecta a la consola desde la que se lanzó e imprime allí el informe. El intérprete no espera a una aplicación de ventana, así que el símbolo del sistema puede volver antes que el informe; si molesta, redirija la salida a un archivo: `BrouserGPUSwitch.exe --diagnostics > report.txt`;
* la configuración y la reversión funcionan como siempre, y los datos se guardan en `%APPDATA%\BrowserGpuSwitch\`;
* el exe se compila para Windows. En Linux, PyInstaller genera un ejecutable sin extensión, pero hay que compilarlo en Linux: `build_exe.bat` no sirve para eso.

### Si el exe no arranca

**«Windows protegió su PC»** (SmartScreen): no es un error de la aplicación. El exe no está firmado con un certificado de firma de código de pago, por eso Windows avisa de un editor desconocido. Pulse «Más información» → «Ejecutar de todas formas». Para distribuirlo públicamente sin ese aviso hace falta firmar el código.

**«Error. Could not create temporary directory!»**: así se comporta la compilación de un solo archivo cuando el sistema o el antivirus impiden descomprimir en el directorio temporal. En esta versión, la compilación de un solo archivo se descomprime no en `%TEMP%`, sino en `%LOCALAPPDATA%`, así que el error debería desaparecer. Si la restricción se mantiene, use el instalador `BrouserGPUSwitch-Setup.exe` o la carpeta `dist\BrouserGPUSwitch\BrouserGPUSwitch.exe`: ninguno descomprime nada. La carpeta se puede compilar a mano:

```bat
python -m PyInstaller --noconfirm --clean packaging\gpu-switch.spec
```

Si hay que llevar el exe a otro equipo, copie la carpeta entera: el exe no arranca sin sus archivos auxiliares al lado.

## Cómo se usa

1. Inicie el programa; el idioma de la interfaz se puede cambiar de inmediato en la lista de la esquina superior derecha de la ventana. Espere a que termine la detección del sistema, los navegadores y las tarjetas gráficas.
2. En el bloque «Seleccione un navegador de los detectados en su PC», elija un navegador.
3. En el bloque «¿A qué acelerador cambiar?» ya está marcada la opción que está vigente ahora mismo.
4. En el bloque «¿A qué acelerador cambiar?», elija la opción que quiera.
5. Si el navegador está en ejecución, el programa pedirá cerrarlo por completo y pulsar «Comprobar de nuevo». El botón «Aplicar» solo se activa cuando terminan los procesos del navegador.
6. Pulse «Aplicar». Aparecerá la ventana «Todo listo, inicie el navegador» con el botón «Iniciar el navegador».
7. Para deshacer los cambios, pulse «Revertir todo» y confirme la acción.

## Qué se cambia exactamente en el sistema

### Windows

Se usa el ajuste de usuario de Windows «Configuración de gráficos»:

```
HKCU\Software\Microsoft\DirectX\UserGpuPreferences
```

* El nombre del valor es la ruta completa al archivo exe del navegador, por ejemplo `C:\Program Files\Google\Chrome\Application\chrome.exe`.
* Los datos del valor son una cadena como `GpuPreference=2;`, donde `0` es predeterminado, `1` es ahorro de energía (gráfica integrada) y `2` es alto rendimiento (gráfica dedicada).
* Los demás campos de la cadena (si los hay) se conservan.
* Al revertir solo se elimina lo que creó la aplicación; si el valor ya existía antes, se restaura su contenido original.

El cambio surte efecto tras reiniciar el navegador por completo. Esta función es compatible con Windows 10 1803+ y funciona en las aplicaciones que usan la selección de GPU del sistema (navegadores basados en Chromium, Firefox y la mayoría de los juegos).

### Linux

Para cada navegador se crea un lanzamiento propio:

* un script envoltorio en el directorio de datos de la aplicación (`~/.config/browser-gpu-switch/wrappers/`);
* un archivo `.desktop` redefinido en `~/.local/share/applications/` con el marcador `X-BrowserGpuSwitch-Mode`.

El envoltorio define las variables de entorno y lanza el navegador original:

* para NVIDIA PRIME Render Offload:
  ```
  __NV_PRIME_RENDER_OFFLOAD=1
  __GLX_VENDOR_LIBRARY_NAME=nvidia
  __VK_LAYER_NV_optimus=NVIDIA_only
  ```
* para DRI_PRIME (AMD/Intel):
  ```
  DRI_PRIME=1
  ```

Al revertir solo se eliminan el envoltorio y el archivo `.desktop` creados por la aplicación. Las redefiniciones ajenas no se tocan: si el navegador ya tiene un archivo `.desktop` de terceros, la aplicación se negará a sobrescribirlo y lo avisará.

## Dónde se guardan los datos

* Windows: `%APPDATA%\BrowserGpuSwitch\`
* Linux: `~/.config/browser-gpu-switch/`
* Para cambiar el directorio: la variable de entorno `BROWSER_GPU_SWITCH_HOME`.

En el directorio están:

* `state.json`: información sobre los ajustes aplicados (necesaria para revertir, también después de reiniciar la aplicación);
* `settings.json`: el idioma de interfaz elegido (se crea tras la primera selección de idioma);
* `backups/`: copias de seguridad de los archivos modificados (Linux).

Si se elimina el directorio a mano, la aplicación pierde la posibilidad de revertir los cambios: use primero «Revertir todo».

## Línea de comandos

```
python main.py                     # обычный запуск
python main.py --mock              # демо-режим, ничего не меняет
python main.py --self-test         # самопроверка без окна, код возврата 0/1
python main.py --diagnostics       # технический отчёт: ОС, GPU, браузеры, процессы, откат
python main.py --ui-smoke-test     # скрытая проверка интерфейса
python main.py --screenshot-mode   # окно для скриншота (демо-данные)
python main.py --platform windows  # принудительно выбрать бэкенд
```

El `BrouserGPUSwitch.exe` compilado acepta las mismas opciones: `BrouserGPUSwitch.exe --self-test`, `BrouserGPUSwitch.exe --diagnostics`, `BrouserGPUSwitch.exe --mock` y las demás. El informe se imprime en la consola desde la que se lanzó el exe; para guardarlo en un archivo: `BrouserGPUSwitch.exe --diagnostics > report.txt`.

## Limitaciones y advertencias

* El ajuste solo afecta al usuario actual. Las demás cuentas no se ven afectadas.
* Windows: algunos programas ignoran el ajuste de GPU del sistema y eligen el adaptador por su cuenta. Es una limitación de Windows, no de la aplicación.
* Linux: el cambio funciona al lanzar el navegador desde el archivo `.desktop` (menú de aplicaciones, dock). Si se lanza desde la terminal sin pasar por el `.desktop`, se usan los ajustes predeterminados.
* Linux + Wayland: el comportamiento depende del compositor y del controlador; en algunos entornos hay que volver a iniciar sesión para que se aplique.
* Las versiones Flatpak/Snap de los navegadores pueden ignorar las variables de entorno por culpa del sandbox.
* NVIDIA PRIME Render Offload requiere tener instalado el controlador propietario de NVIDIA.
* «Predeterminado» no elige una tarjeta gráfica concreta: la decisión queda en manos del sistema operativo.
* La aplicación no instala controladores ni requiere reiniciar.
* El `.exe` compilado no está firmado con un certificado de firma de código: SmartScreen puede mostrar el aviso «Windows protegió su PC» («Más información» → «Ejecutar de todas formas»), y los antivirus a veces dan falsos positivos con las compilaciones de PyInstaller. Para distribuirlo públicamente sin avisos hace falta firmar el código.
* La compilación de un solo archivo se descomprime en cada ejecución, pero no en `%TEMP%`, sino en `%LOCALAPPDATA%`. Si el sistema o el antivirus lo impiden también, use el instalador `BrouserGPUSwitch-Setup.exe` o la carpeta `dist\BrouserGPUSwitch\`: ninguno descomprime nada. Todas las compilaciones las hace `build_exe.bat`; para Linux, `build_linux.sh`.
* No se necesitan permisos de administrador ni para iniciar ni para trabajar. La aplicación solo cambia los ajustes del usuario actual.

## Diagnóstico

Si el navegador no se detecta o el cambio no surte efecto:

```
python main.py --diagnostics
```

El informe contiene el sistema operativo, la lista de GPU, los navegadores encontrados con sus rutas, los procesos en ejecución, las opciones de cambio disponibles, los cambios aplicados y la información de servicio del backend. Autocomprobación:

```
python main.py --self-test
```

## Desarrollo

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

El estilo vive en `app/theme.py`: allí están la paleta de Windows 11 (`#F3F3F3` / tarjetas blancas / acento `#0067C0`), la pila de fuentes `Segoe UI Variable Text → Segoe UI → …`, la escala de espaciados y todos los estilos ttk (tarjetas, botones, combobox, botones de radio, tablas). Los tamaños se recalculan a partir del DPI real; en `app/main.py` se activa la conciencia de DPI antes de crear la ventana, para que el texto siga nítido al 125–150 %. Añada los estilos nuevos ahí, no en `app/ui.py`.

Pruebas:

```
python -m unittest discover -s tests -v
```

Compilar el exe directamente, sin el archivo bat:

```
python -m pip install --upgrade "pyinstaller>=6.0"
python -m PyInstaller --noconfirm --clean packaging/gpu-switch.spec
```

El script `build_exe.bat` hace lo mismo y además la autocomprobación del resultado. Para usar un icono propio en el exe, coloque `packaging/gpu-switch.ico` y el spec lo tomará solo.

Comprobación de sintaxis:

```
python -m compileall app
```

Las pruebas no modifican los ajustes reales: el backend de Windows se prueba con un registro y una lista de procesos simulados, y el de Linux con directorios sysfs/proc simulados y un directorio personal temporal.

### Verificación independiente

Resultados de la revisión de QA, la trazabilidad de los diez requisitos, la cobertura de pruebas y una lista honesta de limitaciones: [docs/qa-report.md](docs/qa-report.md).

Resumen: 236 pruebas OK (1 omitida por el entorno), 44 pruebas de integración y ningún defecto funcional encontrado. La escritura real en el registro de Windows y la comprobación de los procesos en ejecución no se pueden verificar en el sandbox: la lógica se comprobó con un registro y una lista de procesos simulados, así que en un equipo normal se recomienda hacer una ejecución de control.

## Versión

1.0.0
