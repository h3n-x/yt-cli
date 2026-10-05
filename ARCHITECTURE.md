# Arquitectura de yt-cli

## Principios de diseño

1. **Librería, no subproceso, para lo crítico.** `yt-dlp` se usa vía su API Python
   (`yt_dlp.YoutubeDL`), no invocando el binario `yt-dlp` con `subprocess`. Esto evita
   construir comandos por concatenación de strings y da acceso a progreso estructurado
   (`progress_hooks`) en vez de tener que parsear stdout.
2. **ffmpeg sí se invoca como subproceso**, porque no expone una API Python oficial, pero
   siempre con `subprocess.run(args_list, shell=False)` — nunca con una cadena de shell.
3. **Separación estricta entre validación, dominio y presentación.** `core/validators.py`
   no sabe nada de yt-dlp ni de Rich; `cli/main.py` no contiene lógica de negocio, solo
   orquesta.
4. **Configuración y estado como datos, no como código.** Toda opción configurable vive en
   modelos Pydantic (`config/models.py`), nunca como constantes dispersas en el código.
5. **Todo I/O de disco es atómico cuando escribe estado compartido** (config, historial,
   cache): se escribe a un archivo temporal y se hace `rename()`, para no corromper datos
   si el proceso se interrumpe a mitad de escritura. **Desde v0.2.0, además se serializa
   con un lock exclusivo entre procesos** (`utils/locking.py`, vía `fcntl.flock`): el
   patrón anterior era atómico dentro de un proceso pero no entre dos invocaciones
   concurrentes de `yt-cli` (ver AUDIT_REPORT.md, hallazgo B7).

## Capas y módulos

```
cli/            Interfaz de usuario (Typer + Rich). Sin lógica de negocio.
models/         Modelos de datos puros (Pydantic + enums). Sin I/O.
core/           Lógica de dominio: validación, wrapper de yt-dlp, wrapper de ffmpeg.
config/         Carga/guardado de configuración persistente (TOML).
services/       Estado persistente de más alto nivel: historial, cache, cola de descargas.
utils/          Utilidades sin estado: sanitización de nombres, logging, progreso Rich,
                tema visual centralizado (colores/iconos/estilos de tabla).
```

Regla de dependencia: `cli` → `services`/`core`/`config` → `models`/`utils`. Nunca al revés.
`models` y `utils` no importan nada de las capas superiores.

## Flujo de una descarga individual (`yt-cli download URL`)

1. `cli/main.py` carga la configuración (`config.manager.load_config`).
2. Construye un `DownloadRequest` (Pydantic), que en su propia validación llama a
   `core.validators.validate_url`. Si la URL no es de un host soportado, la validación
   falla aquí — antes de tocar la red.
3. `core.downloader.YtDlpDownloader.download()` traduce el `DownloadRequest` a las
   opciones (`ydl_opts`) que espera `yt_dlp.YoutubeDL`, incluyendo:
   - `format`: selector de calidad (`VideoQuality.as_yt_dlp_format()`).
   - `postprocessors`: conversión de audio/video, embebido de miniatura/metadata/capítulos.
   - `progress_hooks`: un callback que traduce el diccionario interno de yt-dlp a un
     `ProgressEvent` propio, desacoplado de la versión de yt-dlp instalada.
4. `utils.progress_ui.RichDownloadProgress` consume esos `ProgressEvent` y actualiza una
   barra Rich con velocidad, ETA y tamaño.
5. Al finalizar, se registra un `HistoryEntry` en `services.history.HistoryStore`
   (si el historial está habilitado en config).

## Concurrencia (`yt-cli batch`)

`yt_dlp.YoutubeDL.extract_info()` es bloqueante (I/O de red + subprocesos ffmpeg). En vez
de reescribir yt-dlp de forma asíncrona, `services.queue.DownloadQueue` ejecuta cada
descarga en un hilo (`loop.run_in_executor`) bajo un `asyncio.Semaphore` que limita la
concurrencia a `network.max_concurrent_downloads`. Esto da paralelismo real porque tanto
la espera de red como la ejecución de ffmpeg liberan el GIL.

## Por qué estas dependencias y no otras

| Dependencia | Por qué se eligió |
|---|---|
| `yt-dlp` | Único extractor de YouTube mantenido activamente y con soporte de postprocesadores ffmpeg integrado. |
| `typer` | CLI declarativa sobre Click, con `--help` automático y tipado, consistente con la UX pedida (estilo `gh`/`uv`). |
| `rich` | Progreso, tablas y colores sin reinventar ANSI a mano. |
| `pydantic` | Validación de configuración y de `DownloadRequest` con mensajes de error claros, en vez de `dict`s sin tipar. |
| `orjson` | Serialización rápida para historial/cache; evita quedarse corto en rendimiento con archivos grandes de historial. |
| `platformdirs` | Rutas XDG correctas (`~/.config`, `~/.cache`, `~/.local/share`) sin hardcodear. |
| `tomli_w` | Escritura de TOML; la lectura usa `tomllib` de la stdlib (3.11+), evitando una dependencia redundante. |
| `httpx` | Reservado para `self-update`/verificación de versión (ver ROADMAP); no se usa aún en el núcleo de descarga. |
| `aiofiles` | Reservado para operaciones de archivo asíncronas en la cola de descargas (ver ROADMAP: hoy la E/S de archivo la maneja yt-dlp/ffmpeg internamente). |

Ninguna dependencia se agregó "por si acaso": las dos últimas están declaradas porque el
enunciado las permite y hay un uso concreto planeado (ver ROADMAP.md), pero se documenta
aquí con honestidad que su integración aún no está completa en el núcleo actual.

## Seguridad por diseño

- `core/validators.py`: lista blanca de esquemas (`http`/`https`) y hosts (`youtube.com`,
  `youtu.be`, `music.youtube.com`). Cualquier otra URL se rechaza antes de llegar a yt-dlp.
- `resolve_safe_path()`: confina cualquier ruta derivada de metadatos (títulos, nombres de
  subida) dentro del directorio de descarga configurado, rechazando `../` y similares.
- `core/converter.py`: `subprocess.run` siempre con lista de argumentos y `shell=False`.
- `utils/naming.py`: sanitiza caracteres de control, nombres reservados de Windows y
  longitud, para que un título de video hostil no pueda romper el sistema de archivos.

## Cambios de diseño en v0.2.0 (ver AUDIT_REPORT.md para el detalle completo)

- **Perfiles de configuración** (`AppConfig.profiles: dict[str, DownloadDefaults]`):
  `--profile <nombre>` resuelve un `DownloadDefaults` alternativo completo en vez de los
  valores globales de `[downloads]`. Se implementó como un `dict` simple en vez de
  herencia/composición entre perfiles (un perfil no puede "extender" otro) para mantener
  la resolución de configuración trivial de razonar; si en el futuro se necesita
  composición, es un cambio localizado en `AppConfig.resolve_downloads()`.
- **Resolución de conflictos de nombre (`RENAME`)**: implementada solo para descargas
  individuales (`_resolve_rename_target` en `core/downloader.py`), no para colecciones.
  Requiere una extracción de metadatos adicional (`extract_metadata_only`) antes de
  descargar, así que solo se activa cuando el usuario configura explícitamente
  `overwrite_policy = "rename"` — para `skip`/`overwrite` no hay costo extra.
- **Backoff exponencial acotado** para reintentos (`_RETRY_SLEEP_FUNCTIONS`), en vez del
  comportamiento por defecto de yt-dlp (reintento inmediato sin pausa), que puede
  agravar fallos transitorios de red martillando el servidor.
- **Locking entre procesos** (`utils/locking.py`): un lock exclusivo POSIX (`fcntl.flock`)
  materializado en un archivo `<target>.lock` companion, con timeout configurable para
  no colgar el proceso ante un lock huérfano.

## Cambios de diseño en v0.3.0

- **`_CliState` (dataclass) en vez de un `dict[str, bool | str | None]` suelto** para el
  estado global de la CLI (`--debug`, `--profile`). El dict original obligaba a un
  `# type: ignore[arg-type]` en cada lectura porque su tipo de valor era una unión sin
  relación con el campo leído; la dataclass tipada elimina la supresión sin perder
  flexibilidad.
- **`DownloadDefaults.model_config = {"validate_assignment": True}`**: necesario para que
  `yt-cli config profile set <perfil> <campo> <valor>` (que hace
  `setattr(perfil, campo, valor_string)`) obtenga la misma coerción de tipos que ya tenía
  `AppConfig` (p. ej. convertir `"flac"` al enum `AudioFormat.FLAC`). Sin esto, el
  `setattr` guardaría un string suelto sin validar — un bug que se habría introducido al
  añadir los subcomandos de perfil si no se hubiera revisado el modelo subyacente.
- **`update`/`self-update` usan la API JSON pública de PyPI** (`GET
  https://pypi.org/pypi/<paquete>/json`) en vez de la API de releases de GitHub que se
  mencionaba como plan en versiones anteriores del ROADMAP: es más simple (no requiere
  autenticación ni paginar assets) y es el índice donde el paquete realmente se
  distribuye. La comparación de versiones usa un parser mínimo propio
  (`_parse_version`) en vez de añadir el paquete `packaging` como dependencia nueva, ya
  que el caso de uso (comparar `X.Y.Z` simples) no lo justifica.
- **`self-update` invoca `pip` como subproceso con lista de argumentos fija**
  (`[sys.executable, "-m", "pip", "install", "--upgrade", "yt-cli"]`, `shell=False`),
  consistente con la regla de seguridad de no construir comandos de shell (ver
  SECURITY.md). No verifica firmas adicionales más allá de la cadena de confianza de
  pip/PyPI — limitación documentada explícitamente, no resuelta.
- **`NO_COLOR`**: ambas instancias de `Console` (`console` y `error_console`) se
  construyen con `no_color=bool(os.environ.get("NO_COLOR"))`, evaluado una vez a nivel de
  módulo. Rich resuelve `sys.stdout`/`sys.stderr` de forma perezosa en cada `print()`, así
  que esto es compatible con la redirección de streams que hace `CliRunner` en los tests.

## Cambios de diseño en v0.3.1 (puramente visual)

- **`utils/theme.py`** centraliza toda decisión de color/icono/estilo de tabla.
  Antes, cada comando de `cli/main.py` elegía sus propios colores ad-hoc
  (`[green]`, `[red]`, `[yellow]` mezclados con `[dim]`/`[bold]` sueltos), lo
  que producía inconsistencias entre comandos (p. ej. `history` y
  `progress_ui.py` usaban paletas de "completado"/"fallido" distintas). Ahora
  ambos importan `status_badge()` del mismo módulo.
- Se decidió **no** usar colores de fondo (`"on <color>"`) para el "zebra
  striping" de las tablas, en favor de `"dim"` en filas alternas: se ve
  correctamente tanto en terminales de tema claro como oscuro sin asumir una
  paleta de fondo concreta.

Ver [SECURITY.md](SECURITY.md) para el proceso de reporte de vulnerabilidades.
