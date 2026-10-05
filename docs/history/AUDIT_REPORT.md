# AUDIT_REPORT.md — Auditoría técnica de yt-cli

## Addendum v0.3.0 (auditoría de seguimiento, motivada por uso real)

Un usuario reportó en producción:

```
zsh: no matches found: https://music.youtube.com/playlist?list=OLAK5uy_...
[1]  + exit 1     yt-cli playlist
```

**Diagnóstico: no es un bug de yt-cli.** Es zsh interpretando `?` como un patrón glob y
`&` como el operador de "ejecutar en segundo plano" *antes* de que el programa se
ejecute — el proceso Python nunca llega a arrancar, por lo que no hay nada que el
código de yt-cli pueda interceptar o corregir. Se verificó que **todos** los ejemplos
de `download`/`audio`/`playlist`/`channel` en README.md ya usaban comillas
correctamente; el problema era puramente de documentación/descubribilidad. Se corrigió
añadiendo una advertencia imposible de no ver al principio del README, una entrada
específica en FAQ.md replicando el mensaje de error exacto, un tip en la salida de
`yt-cli doctor`, y una sección `NOTAS DE USO` en la man page.

Durante esta misma sesión, al escribir la suite de tests de CLI que
`TEST_REPORT.md` (v0.2.0) dejaba explícitamente pendiente, se encontraron y corrigieron
adicionalmente estos bugs reales (ver CHANGELOG.md v0.3.0 para el detalle completo):

| # | Ubicación | Severidad | Descripción |
|---|---|---|---|
| B9 | `cli/main.py::search` | **Media** | Solo capturaba `yt_dlp.utils.DownloadError`; `extract_metadata_only()` puede lanzar también `core.downloader.DownloadError` propio (cuando yt-dlp devuelve `info=None` sin lanzar excepción), que escapaba como excepción no controlada. Encontrado al escribir `test_search_handles_extraction_failure`. |
| B10 | `cli/main.py::doctor` | Baja | Línea muerta `config_dir_writable = ... or True`, siempre verdadera sin comprobar nada. Reemplazada por una comprobación real de escritura. |
| B11 | `config/models.py::DownloadDefaults` | **Media** | Sin `validate_assignment=True`. Al añadir `config profile set` (que hace `setattr` sobre una instancia de este modelo), un `setattr(perfil, "audio_format", "flac")` habría guardado el string crudo sin convertirlo al enum, rompiendo la consistencia de tipos en runtime. Encontrado por revisión propia antes de escribir el test, no por un test que fallara. |
| B12 | `cli/main.py` (tipado) | Baja | `--format`/`--quality` en `download`/`audio` estaban anotados como tipos no-opcionales con `default=None` y un `# type: ignore[assignment]` para silenciar el error real de tipos que eso produce. Corregido a `X \| None`. |
| B13 | `cli/main.py` (tipado) | Baja | El `state` global era un `dict[str, bool \| str \| None]`; leer `state.get("profile")` requería un `# type: ignore[arg-type]` porque el tipo de valor no reflejaba el campo real. Reemplazado por una dataclass tipada. |

Ninguno de estos 5 hallazgos se conocía de antemano; surgieron de escribir tests reales
contra el código real, que es exactamente el propósito de tener una suite de tests de
CLI. Se documentan aquí con el mismo estándar de honestidad que B1–B8 en v0.2.0.

---

# Auditoría original — yt-cli v0.1.0 (secciones originales sin modificar debajo)

**Metodología:** revisión manual línea por línea de los 2076 líneas de `src/` y `tests/`
existentes. No se ejecutó ningún analizador automático (`ruff`/`mypy`/`bandit`) porque el
sandbox de esta sesión no tiene acceso de red para instalar dependencias (`pip install`
falla: `No matching distribution found for hatchling`). Esta limitación se declara aquí y
se repite en `TEST_REPORT.md`: **todo lo marcado como "verificado" en este documento fue
efectivamente ejecutado con `python3` puro sobre stdlib; todo lo marcado como "no
ejecutable en este entorno" es una revisión estática, no una prueba en ejecución.**

## 1. Bugs reales encontrados (confirmados por lectura de código, no supuestos)

| # | Ubicación | Severidad | Descripción |
|---|---|---|---|
| B1 | `core/downloader.py:162` | Baja (código muerto) | Se asigna `opts["nooverwrites"] = True`, una clave que **no existe** en las opciones de `yt_dlp.YoutubeDL` (la clave real es `overwrites`, ya seteada dos líneas antes). yt-dlp ignora claves desconocidas silenciosamente, así que no rompe nada, pero es deuda técnica: sugiere una política que nunca se aplica. |
| B2 | `models/enums.py:80` + `core/downloader.py` | **Media** | `OverwritePolicy.RENAME` existe en el enum y se documenta en `README.md`/`config/models.py` como valor válido, pero **`YtDlpDownloader` nunca lo maneja**. Si un usuario configura `overwrite_policy = "rename"`, el comportamiento real es idéntico a no sobrescribir con nombre distinto — silenciosamente cae en el comportamiento por defecto de yt-dlp. Funcionalidad documentada pero no implementada. |
| B3 | `config/models.py:41` + `core/downloader.py` | **Media** | `NetworkConfig.rate_limit_kbps` se valida y persiste en `config.toml`, pero **`YtDlpDownloader._build_ydl_opts` nunca lo lee**. El usuario puede configurar un límite de velocidad que no tiene ningún efecto. |
| B4 | `core/downloader.py:152` | **Media (UX/correctness)** | Para playlists/canales se fuerza `ignoreerrors=True` (correcto, para que un video privado no aborte toda la playlist), pero el código posterior **no inspecciona qué entradas fallaron**: siempre reporta `DownloadStatus.COMPLETED` para la colección completa aunque la mitad de los videos hayan fallado, y solo se registra **una** entrada de historial para toda la playlist en vez de una por video. |
| B5 | `models/download_request.py` | Baja | `filename_template` no se valida en la construcción del `DownloadRequest`: una plantilla con un placeholder mal escrito (`{tittle}`) sólo falla en tiempo de ejecución dentro de yt-dlp, con un error interno poco claro, en vez de fallar rápido con un mensaje de Pydantic legible. |
| B6 | `utils/naming.py` | Deuda técnica (no es bug de comportamiento, pero es engañoso) | El módulo completo de sanitización de nombres (`render_filename_template`, `sanitize_filename`) está probado y documentado en `ARCHITECTURE.md` como "lo que produce los nombres de archivo finales", pero **nunca se invoca en el flujo real de descarga**: `core/downloader.py._build_output_template` construye el `outtmpl` de yt-dlp directamente y delega toda la sanitización real en el sanitizador interno de yt-dlp. El módulo propio queda como código muerto en el camino feliz. Se corrige usándolo como validación de plantilla en `DownloadRequest` (ver B5) y en la exportación de historial (nueva funcionalidad), en vez de eliminarlo. |
| B7 | `config/manager.py`, `services/history.py`, `services/cache.py` | **Media (race condition real)** | El patrón "leer todo → modificar en memoria → escribir todo (atómico vía `rename()`)" es atómico *a nivel de un único proceso*, pero **no hay ningún lock entre procesos**. Si el usuario ejecuta dos invocaciones de `yt-cli` simultáneamente (p. ej. dos terminales descargando en paralelo), ambas leen el mismo `history.json`, y la que termine de escribir última pisa los cambios de la otra. Esto es una condición de carrera real (TOCTOU) documentada pero no corregida en v0.1.0. |
| B8 | `cli/main.py::search` | Baja | `except Exception as exc` captura absolutamente cualquier excepción (incluyendo `KeyboardInterrupt`... no, `KeyboardInterrupt` no hereda de `Exception`, así que esto es correcto; pero sí captura errores de programación como `AttributeError` por un cambio de esquema de yt-dlp, ocultándolos como si fueran errores de red). Se corrige acotando a `yt_dlp.utils.DownloadError` + `OSError`. |

## 2. Complejidad y diseño

- **No hay duplicación de lógica significativa.** Las 8 capas (`cli`/`models`/`core`/`config`/`services`/`utils`) mantienen la regla de dependencia declarada en `ARCHITECTURE.md`; verificado grepeando imports cruzados — ningún módulo de `models/` o `utils/` importa de `cli/`, `core/` o `services/`.
- **Sobre-ingeniería:** ninguna detectada. El proyecto no tiene capas de abstracción sin uso (no hay interfaces/ABCs especulativas, no hay factories innecesarias).
- **Complejidad innecesaria:** `cli/main.py` tiene funciones (`download`, `audio`) con firmas casi idénticas (7 parámetros repetidos). Es duplicación menor aceptable dado que Typer necesita la firma explícita por comando para generar `--help` correcto; extraerlo a una función genérica perdería la introspección de Typer. Se documenta como decisión consciente, no como deuda.

## 3. Riesgos de seguridad (ver `SECURITY_REPORT.md` para el detalle completo con verificación)

Resumen ejecutivo — de los 10 vectores pedidos en el prompt de auditoría:

| Vector | Estado en v0.1.0 | Acción |
|---|---|---|
| Path traversal | Mitigado (`resolve_safe_path`) pero **no usado en el camino real de descarga** (yt-dlp usa su propio sanitizador) | Documentado en B6; se añade defensa en profundidad (ver SECURITY_REPORT) |
| Command injection | Mitigado correctamente (yt-dlp como librería, ffmpeg con lista de argumentos) | Sin cambios necesarios |
| Unsafe subprocess | Mitigado (`shell=False` explícito) | Sin cambios necesarios |
| Race conditions | **No mitigado** (B7) | Corregido con file locking |
| Symlink attacks | Parcialmente mitigado (`Path.resolve()` sigue symlinks antes de comparar) | Se añade test explícito |
| URLs inválidas | Mitigado (lista blanca de host/esquema) | Sin cambios necesarios |
| Metadata malformada | Parcialmente mitigado (`context.get()` con defaults en `naming.py`, pero ese módulo no está en el camino real — B6) | Corregido al integrar `naming.py` en la validación de plantilla |
| Ataques de nombre de archivo | Mitigado por yt-dlp internamente, pero sin `restrictfilenames` explícito | Se añade opción explícita |
| Inyección TOML | No aplica como vector de inyección (tomli_w serializa, no interpola strings), pero no había test que lo demostrara | Se añade test |
| Argumentos ffmpeg | Mitigado (lista de argumentos fija por formato, sin interpolación de datos de red en las banderas, solo en las rutas de archivo que ya están saneadas) | Sin cambios necesarios |

## 4. Cuellos de botella de rendimiento

Ver `PERFORMANCE_REPORT.md`. Resumen: no se detectó ningún cuello de botella de CPU/memoria
propio del código (el trabajo pesado — red, decodificación, remux — ocurre dentro de
yt-dlp/ffmpeg, fuera del control del proyecto). El único cambio con justificación medible
es reemplazar "reintentos fijos" por backoff exponencial acotado, que reduce presión sobre
la red del usuario y sobre los servidores de YouTube en escenarios de fallo transitorio.

## 5. Gaps funcionales vs. herramientas de referencia

Ver sección `<phase_2_gap_analysis>` en `ROADMAP.md` (actualizado). Resumen de lo
priorizado e implementado en esta iteración: exportación JSON/CSV del historial, perfiles
de configuración con nombre (`--profile`), reintentos con backoff exponencial, límite de
velocidad funcional, manejo correcto de `overwrite_policy=rename`, reporte preciso de
descargas parciales en playlists/canales.

Lo **no** implementado en esta iteración (TUI, scheduler, sistema de plugins, hooks
pre/post descarga, watch mode) se deja explícitamente en `ROADMAP.md` con la justificación
de por qué se deprioriza: son funcionalidades de alto costo de mantenimiento a largo plazo
que no tienen sentido añadir sin antes tener telemetría de uso real de la v0.1.0, y varias
(sistema de plugins) implican decisiones de API pública que no deben tomarse
apresuradamente en una segunda iteración.
