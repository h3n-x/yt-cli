# Roadmap

Este documento distingue explícitamente lo que **ya funciona** de lo que **falta**, para no
generar expectativas falsas sobre el estado del proyecto.

## Implementado y probado (v0.1.0 → v0.3.0)

- [x] Descarga de video/audio individual, con calidad y formato configurables
- [x] Playlists y canales, **con reporte preciso de éxito parcial** (v0.2.0: antes
      siempre reportaban COMPLETED aunque fallaran entradas — ver AUDIT_REPORT.md B4)
- [x] Descarga por lotes (`batch`) con concurrencia real vía cola asíncrona
- [x] Reanudación automática (`continuedl`) y políticas de sobrescritura
      (`skip`/`overwrite`/**`rename` — implementado en v0.2.0, antes definido pero
      no funcional, ver B2**)
- [x] Embebido de miniatura, metadata y capítulos
- [x] Conversión de formatos vía postprocesadores de ffmpeg
- [x] Configuración persistente en TOML, validada con Pydantic
- [x] Perfiles de configuración con nombre (`--profile`, v0.2.0), **gestionables por
      comando desde v0.3.0** (`config profile list/show/set/remove`)
- [x] Historial de descargas y cache de metadatos con TTL
- [x] Exportación de historial a JSON/CSV (v0.2.0), **y salida `--json` también en
      `search`/`history`/`version`** (v0.3.0, para scripting)
- [x] Validación estricta de URLs y rutas (prevención de path traversal / command injection)
- [x] Locking entre procesos para config/historial/cache (v0.2.0, ver B7)
- [x] Rate limiting funcional y reintentos con backoff exponencial (v0.2.0, ver B3)
- [x] Barra de progreso enriquecida (Rich): velocidad, ETA, tamaño
- [x] `doctor` para diagnóstico del entorno (v0.3.0: chequeos reales de escritura,
      versión de Python y espacio en disco; antes tenía una comprobación que siempre
      pasaba sin verificar nada — ver AUDIT_REPORT.md)
- [x] **`update`/`self-update`** reales, vía API de PyPI + `pip install --upgrade` (v0.3.0)
- [x] **`--version` como flag global** además del subcomando `version` (v0.3.0)
- [x] **Soporte de `NO_COLOR`** para accesibilidad (v0.3.0)
- [x] **Tests de `cli/main.py` vía `typer.testing.CliRunner`** (v0.3.0, 34 tests nuevos en
      `tests/test_cli.py` — cierra la brecha que TEST_REPORT.md dejaba pendiente en v0.2.0)
- [x] PKGBUILD, man page y completado bash/zsh/fish

## Pendiente para 1.0

- [ ] **`config init` interactivo** (asistente de primer uso).
- [ ] **Verificación de firma/checksum en `self-update`.** La v0.3.0 delega la integridad
      del paquete completamente en pip + el índice de confianza de PyPI (HTTPS, hashes de
      pip), pero no hace una verificación de firma adicional propia (p. ej. Sigstore).
      Documentado explícitamente en SECURITY.md como limitación conocida, no como algo
      resuelto.
- [ ] **Resolución de conflictos de `RENAME` para playlists/canales.** v0.2.0 implementa
      `RENAME` solo para descargas individuales (video/audio); en colecciones requeriría
      una extracción de metadatos por cada entrada antes de descargar, lo cual es costoso
      en latencia (ver `_resolve_rename_target` en `core/downloader.py`).
- [ ] **Suite de integración contra la red real de YouTube**, gateada detrás de un marcador
      `@pytest.mark.integration` y deshabilitada por defecto en CI (para no depender de
      disponibilidad externa ni violar límites de tasa).
- [ ] **Migración de historial a SQLite** si el volumen de entradas crece lo suficiente
      como para que las consultas sobre JSON dejen de ser eficientes (ver ARCHITECTURE.md).
- [ ] **Uso efectivo de `aiofiles`** para operaciones de archivo propias del proyecto
      (hoy la escritura de archivos multimedia la gestiona yt-dlp/ffmpeg internamente,
      no el código de yt-cli).
- [ ] **CI/CD en GitHub Actions**: el workflow (`ci.yml`) está escrito y es correcto por
      revisión, pero no se ejecutó en esta sesión (sandbox sin acceso al runner de GitHub).
- [ ] **Descarga de livestreams en curso** (yt-dlp lo soporta parcialmente; falta manejo
      explícito de reintentos por segmentos aún no publicados).
- [ ] **Empaquetado AUR real** (publicación en `aur.archlinux.org`, hoy el PKGBUILD es
      funcional pero no está publicado).
- [ ] **Internacionalización** más allá de mensajes en español (el campo `general.language`
      existe en configuración pero aún no se usa para cambiar los strings de la CLI).
- [ ] **Sistema de plugins.** Deliberadamente no implementado en v0.2.0: definir una API
      pública de plugins es una decisión de diseño de alto costo de mantenimiento a largo
      plazo (compatibilidad hacia atrás) que no debe tomarse sin telemetría de uso real.
- [ ] **TUI (Textual), scheduler, watch mode, hooks pre/post descarga.** Ídem: se
      deprioriza deliberadamente hasta tener señal de qué funcionalidades de "prioridad
      media" del roadmap generan demanda real.
