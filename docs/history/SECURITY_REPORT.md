# SECURITY_REPORT.md — yt-cli v0.3.0

## Addendum v0.3.0

- **Nuevo vector cubierto: actualización de software (`self-update`).** `pip` se invoca
  con lista de argumentos fija (`[sys.executable, "-m", "pip", "install", "--upgrade",
  "yt-cli"]`, `shell=False`), consistente con la política de este proyecto. **Limitación
  documentada, no resuelta**: no hay verificación de firma/checksum adicional más allá de
  la cadena de confianza de pip/PyPI (ver ROADMAP.md).
- **`httpx.get()` en `_fetch_latest_pypi_version` tiene `timeout=5.0` por defecto**: evita
  que `update`/`self-update` cuelguen indefinidamente si PyPI no responde.
- **B9 de AUDIT_REPORT.md** (excepción no controlada en `search()`) se reclasifica aquí
  como un hallazgo de robustez, no de seguridad explotable: no permitía ninguna acción no
  autorizada, solo un traceback en vez de un mensaje limpio. Se corrigió de todos modos
  por higiene de manejo de errores (ver CHANGELOG.md v0.3.0).
- El resto de vectores (1–10, ver debajo) no cambiaron respecto a v0.2.0: no se tocó
  `core/validators.py`, `core/converter.py` ni el mecanismo de locking en esta iteración.

---

Este informe cubre los 10 vectores pedidos explícitamente en la fase 3 de auditoría.
Para cada uno: estado, evidencia y, si aplica, qué cambió en esta iteración.

## 1. Path traversal

**Estado: mitigado.** `core/validators.resolve_safe_path()` resuelve cualquier ruta
relativa contra un directorio base con `Path.resolve()` y verifica con
`Path.relative_to()` que el resultado siga dentro del directorio base; si no,
lanza `UnsafePathError`.

**Evidencia (ejecutada en esta sesión, stdlib puro):**
```
>>> resolve_safe_path(Path('/tmp/base'), '../../etc/passwd')
UnsafePathError: la ruta resultante escapa del directorio base
```
Confirmado además con metadatos adversariales de video (uploader conteniendo `/../../`
embebido) a través de `render_filename_template` + sanitización por componente: ningún
componente de ruta resultante es nunca literalmente `..` (ver `test_naming_properties.py`
y la verificación manual equivalente ejecutada en esta sesión).

## 2. Command injection

**Estado: mitigado, sin cambios necesarios.** yt-dlp se invoca como librería Python
(`yt_dlp.YoutubeDL`), nunca como subproceso con argumentos armados a partir de input del
usuario. ffmpeg/ffprobe se invocan vía `subprocess.run` con una lista de argumentos fija
y `shell=False` explícito (`core/converter.py`).

## 3. Unsafe subprocess

**Estado: mitigado, sin cambios necesarios.** Único punto con `subprocess` es
`FFmpegConverter._run()`, con `shell=False` explícito documentado en el propio código.
No hay ningún otro `subprocess`, `os.system`, `os.popen` ni `Popen(..., shell=True)` en
el árbol de `src/` (verificado con `grep -rn "shell=True\|os.system\|os.popen" src/`:
cero resultados).

## 4. Race conditions

**Estado: corregido en v0.2.0 (era el hallazgo más serio de la auditoría, B7).**

Antes: `config/manager.py`, `services/history.py` y `services/cache.py` seguían el
patrón "leer todo → modificar en memoria → escribir todo (atómico vía `rename()`)".
Atómico dentro de un proceso, pero sin coordinación entre procesos.

**Reproducción de la vulnerabilidad (ejecutada en esta sesión):** 20 hilos simulando
escrituras concurrentes de `yt-cli` a un mismo archivo, cada uno hace
leer→incrementar→escribir con una ventana de carrera forzada de 5ms.

```
SIN lock, valor final: 1  (esperado: 20 → 19 escrituras perdidas)
```

**Corrección:** `utils/locking.py` añade `exclusive_lock()` (basado en `fcntl.flock`
sobre un archivo `.lock` companion, con timeout configurable). Se envolvió el ciclo
completo lectura-modificación-escritura en `add()`/`clear()` de `HistoryStore`, `set()`
de `MetadataCache`, y `save_config()`.

**Verificación de la corrección (ejecutada en esta sesión, misma prueba, con el lock):**
```
CON lock, valor final: 20  (correcto)
```

## 5. Symlink attacks

**Estado: mitigado.** `Path.resolve()` sigue symlinks antes de la comparación en
`resolve_safe_path()`; si un symlink dentro del árbol de descarga apunta fuera del
directorio base, la ruta resuelta ya no será relativa al directorio base y se rechaza.
Se añadió un test explícito (`test_resolve_safe_path_rejects_parent_directory_traversal`
más una variante con symlink) a `tests/test_validators.py` para documentar este caso
como comportamiento esperado, no accidental.

## 6. Manejo de URLs inválidas

**Estado: mitigado, sin cambios necesarios.** Lista blanca de esquemas (`http`/`https`)
y hosts (`youtube.com`, `youtu.be`, `music.youtube.com`) en `validate_url()`. Verificado
en esta sesión: rechaza `javascript:`, `file://`, hosts arbitrarios, y el caso adversarial
`youtube.com.evil.com` (que "contiene" la palabra youtube pero no es un subdominio real).

## 7. Metadata malformada

**Estado: mitigado, mejorado en v0.2.0.** `naming.render_filename_template()` usa
`context.get()` con defaults ("untitled", "unknown", etc.) para cualquier campo ausente
o `None`, en vez de fallar. **v0.2.0 corrige B6**: este módulo antes no estaba en el
camino real de descarga (yt-dlp sanitizaba internamente sin pasar por nuestro código);
ahora se usa activamente en la validación de plantilla (`DownloadRequest`) y en la
resolución de conflictos de `RENAME`, por lo que la protección contra metadata
malformada aplica también ahí, no solo en el módulo aislado.

## 8. Ataques de nombre de archivo

**Estado: mitigado.** `sanitize_filename()` reemplaza caracteres de control y
caracteres inválidos multiplataforma (`<>:"/\|?*`), previene nombres reservados de
Windows (`CON`, `PRN`, `COM1`...), recorta longitud excesiva, y colapsa/recorta espacios
y puntos finales. Verificado con batería de casos borde en esta sesión: cadena vacía,
solo puntos/espacios, 500 caracteres, nombres reservados, separadores de ruta embebidos
— todos producen un resultado seguro y, se verificó explícitamente, **idempotente**
(sanear un nombre ya saneado no lo cambia más).

## 9. Inyección TOML

**Estado: no es un vector de inyección viable, verificado.** La configuración se
serializa con `tomli_w.dumps()` sobre un `dict` ya validado por Pydantic — no hay
interpolación de strings de usuario dentro de una plantilla TOML. El único vector
teórico sería un valor de string con caracteres especiales de TOML (comillas, saltos de
línea) que `tomli_w` no escapara correctamente; se añadió un test explícito en
`tests/test_config.py` (round-trip de un `filename_template` con comillas y backslashes)
para documentar y fijar este comportamiento.

## 10. Seguridad de argumentos de ffmpeg

**Estado: mitigado, sin cambios necesarios.** Las banderas de ffmpeg (`-c:v`, `-c:a`,
códecs, etc.) están fijas por formato en diccionarios estáticos
(`_AUDIO_CODECS`, `_VIDEO_CONTAINER_ARGS`); los únicos valores derivados de datos
externos son las *rutas* de archivo (`source`, `destination`), que ya pasan por
`resolve_safe_path()` antes de llegar aquí. Ningún dato de red se interpola dentro de
una bandera de ffmpeg.

## Resumen

| # | Vector | Estado |
|---|---|---|
| 1 | Path traversal | Mitigado |
| 2 | Command injection | Mitigado |
| 3 | Unsafe subprocess | Mitigado |
| 4 | Race conditions | **Corregido en v0.2.0** |
| 5 | Symlink attacks | Mitigado |
| 6 | URLs inválidas | Mitigado |
| 7 | Metadata malformada | Mitigado (uso reforzado en v0.2.0) |
| 8 | Ataques de nombre de archivo | Mitigado |
| 9 | Inyección TOML | No es un vector viable (verificado) |
| 10 | Argumentos ffmpeg | Mitigado |

**Nota de honestidad metodológica:** los puntos 1, 6, 8 y la reproducción/corrección del
punto 4 se ejecutaron literalmente con `python3` en esta sesión (ver transcripción de
comandos). Los puntos 2, 3, 5, 7, 9, 10 son verificación estática por lectura de código
(grep + revisión manual), no ejecución, porque no dependen de lógica nueva compleja sino
de la ausencia de un patrón (p. ej. "no hay ningún `shell=True`"), verificable de forma
determinística sin ejecutar el programa.
