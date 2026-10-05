# Arquitectura de yt-cli

## Principios de diseño

1. **yt-dlp como librería, no como subproceso.** Se usa `yt_dlp.YoutubeDL`: no se
   construyen comandos por concatenación de strings y el progreso llega estructurado
   (`progress_hooks`) en vez de parsear stdout.
2. **Ningún texto de yt-dlp llega directo a la terminal.** El downloader entrega a
   yt-dlp un logger propio (`_YtDlpLogBridge`) y desactiva sus colores; los errores se
   recogen, se limpian y se traducen (`core/errors.py`) y la CLI los muestra **una sola
   vez**. Todo texto externo (títulos, errores) se escapa antes de pasar por Rich.
3. **Dos ejes independientes en cada descarga:** `MediaType` (video/audio) y `Scope`
   (single/playlist/channel). El alcance se deduce de la URL
   (`utils/validators.detect_scope`), así que `audio` sobre una playlist hace lo esperado.
4. **Configuración y estado como datos validados** (Pydantic). Toda opción de la
   configuración tiene efecto; un test de contrato falla si alguna queda sin usar.
5. **Escrituras atómicas y serializadas entre procesos** para config, historial y cache:
   archivo temporal + `rename()` bajo un `fcntl.flock` (`utils/locking.py`).
6. **Arranque rápido:** yt-dlp, httpx y asyncio se importan dentro de los comandos que los
   usan; `--help`, `config` y el autocompletado no los cargan.

## Capas y módulos

```
cli/
  main.py            entry point (run), opciones globales, registra los módulos de comandos
  _app.py            Typer app, consolas, estado global, helpers de salida, códigos de salida
  download_cmds.py   download, audio, playlist, channel, batch, search (+ preflight, resumen)
  config_cmds.py     config show/set/path, config profile …
  history_cmds.py    history (…/export/clear), cache stats/clear
  system_cmds.py     doctor, version, update, self-update
services/
  download_service.py  config → YtDlpDownloader / DownloadRequest; registro en historial
  queue.py             DownloadQueue: TaskGroup + hilos, cancelación, aislamiento de fallos
  history.py           history.json (orjson), filas por video, export JSON/CSV
  cache.py             cache con TTL (resultados de search)
core/
  downloader.py      YtDlpDownloader: opciones, postprocesadores, colecciones, RENAME
  errors.py          limpieza y traducción de errores de yt-dlp
  dependencies.py    ffmpeg, runtime JS, mutagen, antigüedad de yt-dlp
config/
  models.py          AppConfig / DownloadDefaults / NetworkConfig / GeneralConfig / [ytdlp]
  manager.py         carga/guardado TOML (0600)
models/
  enums.py           MediaType, Scope, formatos, calidades, estados, DownloadKind (historial)
  download_request.py DownloadRequest validado (URL, plantilla, rango)
  results.py         ProgressEvent, DownloadResult, EntryResult
utils/
  validators.py      lista blanca de URLs, detect_scope, resolve_safe_path (sin dependencias)
  naming.py          validación/render de plantillas propias
  progress_ui.py     barras Rich (texto externo escapado)
  logging.py, locking.py, theme.py
```

**Regla de dependencias:** `cli → services → core → models/utils`. `models` y `utils`
nunca importan de `core`, `services` ni `cli`, ni importan yt-dlp (`progress_ui` y
`theme` usan los tipos de `models`; `download_request` usa los validadores puros de
`utils`).

## Flujo de una descarga (`yt-cli audio "<playlist de YouTube Music>"`)

1. `cli/download_cmds.audio` carga la configuración y el perfil (`--profile`).
2. `services.download_service.build_request` valida la URL, deduce `Scope.PLAYLIST` y
   construye el `DownloadRequest` (plantilla de playlist, archivo de descargas si aplica).
3. `_preflight` comprueba ffmpeg (error) y avisa si falta un runtime JS o `mutagen`.
4. `YtDlpDownloader.download` → `download_collection`: opciones con
   `ignoreerrors=True`, `FFmpegExtractAudio`, carátula solo si el contenedor la admite.
5. yt-dlp procesa cada entrada; las que fallan quedan como `None` en `entries` y su error
   pasa por el log bridge. Las ya registradas en el archivo de descargas se marcan como
   `SKIPPED`, no como fallo.
6. El resultado lleva un `EntryResult` por video; el historial guarda una fila por video
   (con la URL del video) en una sola escritura.
7. La CLI imprime el resumen (`N descargadas · M fallidas`) con la causa de cada fallo y
   sale con 0, 1, 3 o 130.

## Nombres de archivo

La ruta real la decide yt-dlp (`outtmpl`, traducido desde la plantilla propia en
`build_output_template`). Para `overwrite_policy = "rename"` se usa
`YoutubeDL.prepare_filename` —la misma sanitización que la descarga real— y se añade
` (n)` si el archivo existe. `utils/naming.py` solo valida la sintaxis de las plantillas
(placeholders simples, sin acceso a atributos ni especificadores de formato).

## Concurrencia (`yt-cli batch`)

`DownloadQueue` ejecuta cada descarga con `asyncio.to_thread` bajo un `Semaphore`
(`network.max_concurrent_downloads`) dentro de un `TaskGroup`. Una excepción inesperada se
convierte en un resultado FAILED para esa URL. Ante Ctrl+C la cola llama a
`downloader.cancel()`: el siguiente progress hook de cada hilo lanza `DownloadCancelled`,
así que los hilos terminan en segundos y la salida no queda bloqueada.

## Por qué estas dependencias

| Dependencia | Motivo |
|---|---|
| `yt-dlp` | Extractor de YouTube mantenido activamente, con postprocesadores ffmpeg. |
| `mutagen` | yt-dlp lo necesita para incrustar carátulas en opus/ogg/flac. |
| `typer` + `rich` | CLI declarativa con ayuda, autocompletado, tablas y progreso. |
| `pydantic` | Validación de configuración y solicitudes con mensajes claros. |
| `orjson` | Historial y cache rápidos. |
| `platformdirs` | Rutas XDG correctas. |
| `tomli-w` | Escritura de TOML (la lectura usa `tomllib` de la stdlib). |
| `httpx` | Consulta a PyPI en `update`/`self-update` (importado solo ahí). |

## Seguridad por diseño

Ver [SECURITY.md](SECURITY.md).
