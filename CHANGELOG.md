# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).
Este proyecto sigue [Semantic Versioning](https://semver.org/lang/es/).

## [0.4.0] - 2026-10-05

Versión de correcciones a partir de una auditoría basada en ejecución real
([docs/AUDIT_2026-10.md](docs/AUDIT_2026-10.md)), motivada por un fallo reportado al
descargar una playlist de YouTube Music.

### Corregido

- **Una playlist con un video no disponible abortaba la descarga completa**
  (`yt-cli audio "<playlist>"`): el alcance (video/playlist/canal) ahora se deduce de la
  URL y en toda colección se continúa con el resto de entradas.
- **Errores repetidos hasta 4 veces y con basura ANSI** (`[1m[0;31mERROR:`): yt-dlp ya no
  escribe en la terminal; cada error se muestra una vez, limpio, con el id del video y
  una pista de qué hacer.
- **El logging interpretaba markup de Rich**: se perdía `[youtube]` de los mensajes y un
  texto con `[/algo]` lanzaba `MarkupError` y abortaba la descarga. Los títulos tampoco
  pueden inyectar estilos en la barra de progreso.
- **`-f opus/ogg/flac` fallaba al final sin `mutagen`, y `-f wav/aac` o video `webm`
  fallaban siempre** al intentar incrustar la carátula: solo se incrusta donde yt-dlp
  puede hacerlo, y `mutagen` es ahora dependencia.
- **`self-update` instalaba cualquier paquete llamado `yt-cli` en PyPI** (el nombre no
  estaba registrado): ahora exige que el paquete declare este repositorio, instala la
  versión exacta comprobada y se niega si yt-cli no se instaló con pip o si el Python es
  el del sistema (PEP 668).
- **Autocompletado empaquetado no funcional** (usaba el protocolo de Click): ahora se
  genera desde Typer y un test lo verifica.
- **Ctrl+C** mostraba un traceback o dejaba `batch` bloqueado hasta 5 minutos: salida
  limpia con código 130 y cancelación de las descargas en curso.
- `overwrite_policy = "rename"` comprobaba un nombre distinto del que escribía yt-dlp;
  ahora usa `prepare_filename` de yt-dlp.
- Un `/` en un título creaba subdirectorios en las plantillas propias.
- Validación de URLs por *hostname*: se aceptan `:443`, `usuario@` y `youtube-nocookie.com`;
  se rechazan puertos no numéricos.
- `batch` con URLs repetidas dejaba una barra sin terminar; con un directorio o un archivo
  inexistente fallaba con traceback.
- Una excepción inesperada en una descarga de `batch` perdía el resumen completo.
- El historial de colecciones guardaba la URL de la playlist en cada fila; ahora la del
  video. Un `history.json` dañado da un error claro.
- `search` y RENAME ignoraban proxy y cookies.
- Errores de disco (disco lleno, permisos) se muestran como fallo de la descarga, no como
  traceback.
- Las PKGBUILD/README/CI apuntaban a un repositorio inexistente y la CI no podía pasar.

### Añadido

- `playlist`/`channel`: `--audio`, `--format`, `--quality`.
- `--items` (rango de entradas) y `--archive/--no-archive` (no repetir descargas) en
  todos los comandos de descarga; `downloads.use_download_archive`.
- `downloads.sponsorblock_remove`, `network.cookies_from_browser` y sección `[ytdlp]`
  para opciones adicionales de yt-dlp.
- Posición `n/N` en la barra de progreso de colecciones y resumen final con la causa de
  cada fallo; `history --failed`.
- `doctor`: runtime JavaScript, `mutagen` y antigüedad de yt-dlp; avisos previos a la
  descarga si faltan.
- `history export --force` (ya no sobrescribe sin pedirlo).
- `config set <clave> none` restablece el valor por defecto.
- Workflow de release con PyPI Trusted Publishing y attestations.

### Cambiado

- **Código de salida 3** (antes 2) para colecciones parcialmente completadas: 2 es el
  código de error de uso de Click. Ver la tabla de códigos en README y `man yt-cli`.
- La cache (`general.cache_enabled`, `cache_ttl_hours`) ahora guarda los resultados de
  `search`; antes no se usaba en ningún flujo.
- `config.toml` se escribe con permisos 0600 y `config show` oculta credenciales de proxy.
- CLI dividida en módulos (`cli/*_cmds.py`) y capa `services/download_service.py`;
  imports pesados diferidos: `config`/`version`/`history` arrancan en ~240 ms (antes ~380).
- `pyproject.toml`: versión única (`src/yt_cli/__init__.py`), licencia SPDX (PEP 639),
  `[dependency-groups]`, URLs del proyecto, Python 3.14; `yt-dlp>=2025.11.12`.
- CI: ruff + ruff format + mypy strict, tests en 3.13 y 3.14 con cobertura ≥ 88 %, prueba
  del wheel y `makepkg` real en un contenedor de Arch.
- Informes antiguos no verificados movidos a `docs/history/`.

### Eliminado

- Opciones sin efecto: `general.language`, `general.check_for_updates` (se ignoran si
  siguen en un `config.toml` existente).
- `core/converter.py` (`FFmpegConverter`, nunca usado) y la dependencia `aiofiles`.
- `HistoryStore.find_by_url` (sin usos; el archivo de descargas cubre ese caso).

## [0.3.1] - 2026-07-20

Iteración puramente visual/estética, a pedido explícito: **sin cambios de
comportamiento, lógica de negocio, API pública ni datos persistidos.**

### Añadido

- **`utils/theme.py`** (nuevo módulo): paleta de colores semánticos centralizada
  (`success`/`error`/`warning`/`info`/`accent`/`muted`/`title`/`header`/`border`/
  `value`/`url`), iconos y estilo consistentes por `DownloadStatus`
  (`status_badge()`), y constantes de tabla compartidas (`TABLE_BOX`,
  `ZEBRA_ROW_STYLES`). Cada nombre de color se verificó individualmente contra
  `rich.color.ANSI_COLOR_NAMES` antes de usarse, y cada componente visual nuevo
  (tema, tablas, panel de versión, badges de estado) se renderizó con una copia
  real de Rich para confirmar que no lanza `MarkupError` ni `ColorParseError`.
- Helpers `_success()` / `_warn()` / `_info()` en `cli/main.py`, con icono y
  color consistentes, reemplazando ~20 llamadas a `console.print` con colores
  hardcodeados y mezclados (`[green]`, `[red]`, `[yellow]`, `[dim]`, `[bold]`)
  repartidos de forma inconsistente por el archivo.
- Tablas (`search`, `config profile list`, `history`, `doctor`) con bordes
  redondeados, encabezado y bordes con color de tema, "zebra striping" tenue en
  filas alternas, y truncado con elipsis en columnas de texto largo (título,
  ruta) para que no rompan el ancho de la terminal.
- `yt-cli version`: reescrito como un panel tipo "about box" (inspirado en la
  estética de `cargo`/`uv`) en vez de líneas de texto plano.
- `yt-cli doctor`: el tip sobre comillas de shell ahora va en un `Panel`
  destacado en vez de una línea de texto atenuado fácil de pasar por alto.
- Separadores de sección (`console.rule`) antes de `config show` y al iniciar
  la descarga de una playlist/canal, para marcar visualmente el inicio de cada
  bloque de salida.
- Barra de progreso (`utils/progress_ui.py`): separadores `•` entre columnas,
  colores de barra por estado (en progreso / completado), y los mismos iconos
  de estado que el resto de la CLI (antes tenía su propia combinación de
  colores hardcodeada, distinta de `history`/`doctor`).
- Mensajes de estado vacío (`search` sin resultados, historial vacío, sin
  perfiles) reclasificados de "advertencia" a "informativo" (ícono `ℹ` en vez
  de `⚠`): no son un problema, son un estado neutral.

### Sin cambios (deliberado, y verificado)

- Ninguna función de `core/`, `config/`, `services/` ni `models/` se modificó.
- Ningún test cambió su aserción de comportamiento (solo se verificó que la
  suite completa sigue compilando tras el refactor visual).
- El formato de `config.toml`, `history.json` y la cache no cambió.
- Se re-ejecutó el chequeo de imports no usados y `py_compile` sobre los 12
  archivos de test y todos los módulos de `src/` tras el refactor: limpio.

## [0.3.0] - 2026-07-08

Tercera iteración, motivada por uso real reportado por un usuario (error de shell al
pasar URLs sin comillas) y una ronda adicional de auditoría propia mientras se
escribían los tests de CLI que quedaron pendientes en v0.2.0.

### Corregido

- **Bug real encontrado al escribir `tests/test_cli.py`**: `search()` solo capturaba
  `yt_dlp.utils.DownloadError`, pero `extract_metadata_only()` puede lanzar también
  nuestro propio `core.downloader.DownloadError` (cuando yt-dlp devuelve `info=None`
  sin lanzar excepción). Antes de este fix, ese caso escapaba como una excepción no
  controlada en vez de un mensaje de error limpio.
- **`doctor`**: la comprobación de "directorio de config escribible" tenía una línea
  muerta (`... or True`, siempre verdadera sin comprobar nada real). Ahora intenta
  escribir un archivo de prueba de verdad. Se añadieron además comprobaciones de
  versión de Python y espacio en disco libre en el directorio de descarga.
- **Tipado de `--format`/`--quality`** en `download`/`audio`: estaban anotados como
  `VideoFormat`/`AudioFormat` (no opcional) con `default=None` y un
  `# type: ignore[assignment]` para silenciar el error de tipos. Se corrigió la
  anotación a `X | None`, que es lo que realmente son.
- **`DownloadDefaults` sin `validate_assignment`**: al añadir los subcomandos
  `config profile set` (que hacen `setattr` sobre una instancia de `DownloadDefaults`),
  se detectó que ese modelo no validaba/coercía asignaciones como sí lo hace
  `AppConfig`. Sin este fix, `config profile set archivo audio_format flac` habría
  guardado el string `"flac"` sin convertirlo al enum `AudioFormat.FLAC`.
- **`state` global suelto (`dict[str, bool | str | None]`)** reemplazado por una
  dataclass tipada (`_CliState`), eliminando un `# type: ignore[arg-type]` real.

### Añadido

- **`yt-cli config profile list|show|set|remove`**: antes los perfiles con nombre solo
  se podían crear editando `config.toml` a mano (no había forma de crearlos vía
  `config set` porque `profiles` es un `dict`, no un objeto con atributos).
- **`yt-cli update`** y **`yt-cli self-update`**: consultan la API pública de PyPI y,
  en el segundo caso, instalan la versión más nueva vía `pip install --upgrade` (lista
  de argumentos fija, nunca un comando de shell). Ver limitación documentada en
  SECURITY.md (sin verificación de firma adicional más allá de pip/PyPI).
- **`--version`** como flag global, además del subcomando `version` existente.
- **`--json`** en `search`, `history` y `version`, para scripting.
- **Soporte de `NO_COLOR`** (https://no-color.org/): con la variable de entorno
  definida, toda la salida (incluidos los errores) se imprime sin colores ANSI.
- **Advertencia prominente sobre comillas de URL** en README/FAQ/`doctor`, en respuesta
  directa a un error real reportado por un usuario (`zsh: no matches found: ...` al
  pasar una URL con `&`/`?` sin comillas). No es un bug de yt-cli — ocurre en cualquier
  programa de línea de comandos — pero se documenta de forma muy visible porque es la
  fuente de confusión más probable para un usuario nuevo.

### Tests

- **`tests/test_cli.py`** (34 tests nuevos): primera suite de tests que ejercita
  `cli/main.py` directamente vía `typer.testing.CliRunner`, cerrando la brecha que
  `TEST_REPORT.md` dejaba explícitamente pendiente en v0.2.0. Cubre: versión, config,
  perfiles, historial (incluida exportación), validación de descargas, `doctor`,
  `update`/`self-update` (con `subprocess.run` mockeado para verificar que nunca se
  construye un comando de shell), y `search --json`.
- **`tests/test_version_parsing.py`** (4 tests): la función `_parse_version` es
  puro-stdlib y se verificó también con un script manual directo en esta sesión (ver
  TEST_REPORT.md).
- Total de tests del proyecto: 96 → **134**.

### Sin cambios (deliberado)

- No se tocó la arquitectura de capas ni se reemplazó ninguna dependencia existente.
- No se eliminó ninguna funcionalidad de versiones anteriores.

## [0.2.0] - 2026-07-07

Segunda iteración: auditoría técnica completa de v0.1.0 (ver `AUDIT_REPORT.md`)
seguida de correcciones reales sobre el mismo código, no un rediseño paralelo.

### Corregido

- **B1**: eliminada la clave `nooverwrites` en `core/downloader.py`, que no existe en
  `yt_dlp.YoutubeDL` y no tenía ningún efecto (código muerto).
- **B2**: `OverwritePolicy.RENAME` estaba definido en el modelo de configuración pero
  nunca se implementaba; ahora `YtDlpDownloader._resolve_rename_target()` calcula el
  nombre final real (vía metadatos + `naming.render_filename_template`) y agrega un
  sufijo numérico `(1)`, `(2)`... si el archivo ya existe.
- **B3**: `network.rate_limit_kbps` se validaba y persistía en configuración pero nunca
  se pasaba a yt-dlp; ahora se traduce a `ratelimit` (bytes/segundo) en las opciones
  reales de descarga.
- **B4**: las descargas de playlists/canales reportaban siempre `COMPLETED` aunque
  fallaran entradas individuales. Ahora se introduce `DownloadStatus.PARTIAL` y se
  registra una entrada de historial por cada video de la colección, no una sola fila
  agregada.
- **B5**: una plantilla de nombre de archivo con un placeholder inválido (p. ej.
  `{tittle}`) solo fallaba en tiempo de ejecución dentro de yt-dlp; ahora
  `DownloadRequest` la valida en construcción y falla rápido con un error claro.
- **B6**: `utils/naming.py` (sanitización de nombres) estaba probado pero nunca se
  invocaba en el camino real de descarga; ahora se usa activamente para validar
  plantillas, resolver conflictos de `RENAME`, y en la exportación de historial.
- **B7 (seguridad — condición de carrera real)**: dos invocaciones concurrentes de
  `yt-cli` podían pisarse mutuamente el historial/configuración/cache (patrón
  leer-todo→modificar→escribir-todo sin coordinación entre procesos). Se añadió
  `utils/locking.py` (basado en `fcntl.flock`) y se envolvió el ciclo completo de
  lectura-modificación-escritura en `config/manager.py`, `services/history.py` y
  `services/cache.py`. Verificado con una prueba de concurrencia real (20 hilos): sin
  el fix, el valor final observado fue 1/20 (escrituras perdidas); con el fix, 20/20.
- **B8**: `search` y `config set` capturaban `Exception` genérico, ocultando errores de
  programación como si fueran errores de red o de validación esperados. Acotado a las
  excepciones específicas relevantes en cada caso.

### Añadido

- `network.rate_limit_kbps` ahora tiene efecto real (ver B3).
- Reintentos con backoff exponencial acotado (`http`: hasta 60s, `fragment`: hasta 30s,
  `file_access`: hasta 10s) en vez de reintento inmediato sin pausa.
- Perfiles de configuración con nombre (`[profiles.<nombre>]` en `config.toml`,
  flag global `--profile`/`-p`), para alternar entre presets (p. ej. "archivo": FLAC +
  mejor calidad vs. "rápido": 480p).
- `yt-cli history export <archivo> --format json|csv`.
- `yt-cli history clear` (antes listado como pendiente en el roadmap de v0.1.0).
- `DownloadStatus.PARTIAL` para reportar con precisión descargas de colecciones con
  éxito parcial; código de salida `2` distinto de `1` (fallo total) en ese caso.

### Tests

- +55 tests nuevos (locking bajo concurrencia real, backoff, resolución de conflictos
  de `RENAME`, resumen de colecciones parciales, perfiles, exportación de historial,
  validación temprana de plantillas, property-based tests con Hypothesis para
  `sanitize_filename`/`render_filename_template`).
- Ver `TEST_REPORT.md` para el desglose honesto de qué se ejecutó realmente en esta
  sesión (stdlib puro: `naming`, `validators`, `locking`, backoff) y qué quedó escrito y
  revisado pero pendiente de ejecución en CI por falta de red para instalar
  `pydantic`/`yt-dlp`/`hypothesis` en este sandbox.

### Sin cambios (deliberado)

- No se tocó la arquitectura de capas (`cli`/`models`/`core`/`config`/`services`/`utils`).
- No se reemplazó yt-dlp, ffmpeg, ni ninguna dependencia existente.
- No se eliminó ninguna funcionalidad de v0.1.0.

## [0.1.0] - 2026-07-05

### Añadido

- Comandos: `download`, `audio`, `playlist`, `channel`, `batch`, `search`, `config`
  (`show`/`set`/`path`), `history`, `cache` (`stats`/`clear`), `doctor`, `version`.
- Wrapper seguro sobre la API Python de yt-dlp con selección de calidad/formato,
  postprocesadores de conversión, embebido de miniatura/metadata/capítulos y subtítulos.
- Wrapper seguro sobre ffmpeg/ffprobe para conversión puntual, sin invocación de shell.
- Sistema de configuración persistente en TOML validado con Pydantic.
- Historial de descargas y cache de metadatos con TTL configurable.
- Cola de descargas concurrente basada en asyncio + `ThreadPoolExecutor`.
- Validación estricta de URLs (lista blanca de hosts) y de rutas (prevención de path
  traversal).
- Sanitización de nombres de archivo multiplataforma (Linux/macOS/Windows).
- Barra de progreso enriquecida vía Rich (velocidad, ETA, tamaño).
- Empaquetado Arch Linux: PKGBUILD, man page, completado bash/zsh/fish.
- Suite de tests para lógica pura (validadores, naming, enums, configuración, historial,
  cache, modelo de solicitud de descarga).

### Pendiente

Ver [ROADMAP.md](ROADMAP.md).
