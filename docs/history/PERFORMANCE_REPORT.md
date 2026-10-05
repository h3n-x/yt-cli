# PERFORMANCE_REPORT.md — yt-cli v0.3.0

## Addendum v0.3.0

Cambios de esta iteración sin impacto de rendimiento medible: `config profile`
(operaciones sobre un `dict` en memoria + el mismo guardado TOML atómico ya existente),
`update`/`self-update` (una única petición HTTP GET con timeout de 5s, fuera del camino
crítico de descarga), `--json` en `search`/`history`/`version` (mismo trabajo que la
tabla Rich, solo cambia el formato de salida). No se identificaron cuellos de botella
nuevos ni se requirió ninguna optimización en esta iteración.

---

## Metodología

No se ejecutó ningún profiler (`cProfile`, `py-spy`, `memory_profiler`) en esta sesión:
requerirían descargas reales de red (yt-dlp/ffmpeg no están instalados en este sandbox
sin acceso a red). Este informe es, por lo tanto, un análisis estático de dónde puede
estar el tiempo/memoria y qué cambios tienen una justificación técnica clara — no una
medición empírica con números de wall-clock. Se marca explícitamente cada afirmación
como "medido" o "por diseño/análisis".

## Dónde se gasta el tiempo (por diseño, no medido)

El código de yt-cli en sí mismo hace muy poco trabajo pesado: el 95%+ del tiempo de
ejecución de cualquier comando de descarga ocurre dentro de yt-dlp (red, extracción de
metadatos) y ffmpeg (remux/transcodificación), ambos fuera del control directo del
proyecto. Esto ya se documentaba en la iteración anterior y sigue siendo cierto.

## Cambios de esta iteración con justificación de rendimiento

### 1. Backoff exponencial en reintentos (en vez de reintento inmediato)

**Antes:** yt-dlp, sin `retry_sleep_functions` configurado, reintenta inmediatamente sin
pausa entre intentos ante un fallo transitorio (timeout, 5xx). Ante una degradación de
red sostenida, esto puede generar una ráfaga de reintentos inmediatos consecutivos.

**Después:** `_RETRY_SLEEP_FUNCTIONS` (ver `core/downloader.py`) espera
`min(4 * 2^n, 60)` segundos entre reintentos HTTP, `min(2 * 2^n, 30)` para fragmentos.

**Justificación:** esto no es una optimización de velocidad (de hecho, introduce pausas
donde antes no las había) — es una corrección de *comportamiento cortés hacia el
servidor remoto* y de *robustez ante fallos transitorios*, evitando que yt-cli agrave un
problema de red ya existente. Se documenta aquí y no como "mejora de seguridad" porque
su motivación es explícitamente de rendimiento/fiabilidad de red, no de seguridad del
usuario.

**Verificado (ejecutado en esta sesión):** las funciones de backoff están correctamente
acotadas — `http` nunca excede 60s, `fragment` nunca excede 30s, `file_access` nunca
excede 10s, y crecen monótonamente hasta el techo (ver transcripción de la sesión:
`[4, 8, 16, 32, 60, 60, ...]`).

### 2. Locking entre procesos (fcntl.flock)

**Costo añadido:** cada `add()`/`set()`/`save_config()` ahora abre un file descriptor
adicional (`<archivo>.lock`) y hace una llamada de sistema `flock()`. Esto es una
operación de microsegundos en Linux; no es medible frente al costo de I/O de red o disco
que ya domina estas operaciones (escribir un historial de unos pocos KB).

**Trade-off aceptado conscientemente:** en el caso raro de que un proceso muera mientras
sostiene el lock (p. ej. `kill -9`), el lock POSIX se libera automáticamente al cerrarse
el file descriptor (comportamiento estándar de `flock` en Linux: los locks no sobreviven
al cierre de todos los descriptores del proceso), así que no hay riesgo de "lock
huérfano permanente" — pero sí se añadió un timeout (`10s` por defecto) como defensa en
profundidad ante el caso de un proceso colgado (no muerto) que sostenga el lock más de
lo esperado.

### 3. Extracción de metadatos adicional para `overwrite_policy=rename`

**Costo añadido, real y no trivial:** `_resolve_rename_target()` hace una llamada
`extract_info(skip_download=True)` adicional *antes* de la descarga real, cuando el
usuario elige explícitamente la política `rename`. Esto añade una ronda de red completa
(típicamente 0.5–2s contra la API de YouTube) que no existía antes.

**Justificación del trade-off:** se activa *solo* cuando el usuario elige `rename`
explícitamente (no es el valor por defecto, que es `skip`); para `skip`/`overwrite` no
hay ningún costo adicional. Se documenta explícitamente en `ARCHITECTURE.md` como una
decisión consciente, no un descuido.

## Cuellos de botella identificados y NO corregidos (con justificación de por qué no)

- **`services/history.py`: `_read_all()` parsea el JSON completo en cada `add()`.** Para
  un historial de miles de entradas, esto es O(n) por escritura. **No se corrigió**
  porque el volumen esperado (historial personal de un usuario) hace este costo
  insignificante frente al de la propia descarga; migrar a SQLite antes de tener
  evidencia real de que el archivo crece lo suficiente sería optimización prematura (ver
  ROADMAP.md, donde se deja como ítem condicional).
- **`services/cache.py`: un archivo por entrada de cache.** Para cachés con miles de
  entradas, esto puede acercarse a límites de inodos en sistemas de archivos con cuotas
  estrictas. No se corrigió por la misma razón: no hay evidencia de que el volumen real
  lo justifique, y el diseño actual tiene la ventaja de permitir invalidar entradas
  individuales sin parsear un archivo monolítico.

## Concurrencia (sin cambios respecto a v0.1.0, sigue siendo válido)

`DownloadQueue` (services/queue.py) sigue usando `asyncio.Semaphore` +
`loop.run_in_executor` para paralelizar descargas bloqueantes de yt-dlp. No se
encontraron problemas nuevos aquí durante la auditoría; el diseño de v0.1.0 se mantiene
sin cambios.
