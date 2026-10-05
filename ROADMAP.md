# Roadmap

Distingue lo que **funciona y está probado** de lo que **falta**. La auditoría que
originó la versión 0.4.0 está en [docs/AUDIT_2026-10.md](docs/AUDIT_2026-10.md).

## Implementado (≤ 0.4.0)

- [x] Video y audio individuales con formato y calidad configurables
- [x] Playlists, álbumes de YouTube Music y canales **en video o en audio**; las entradas
      no disponibles no detienen el resto y se informan con su causa (0.4.0)
- [x] Detección automática de playlist/canal a partir de la URL (0.4.0)
- [x] Rango de entradas (`--items`) y archivo de descargas (`--archive`) (0.4.0)
- [x] Descarga por lotes concurrente, con cancelación limpia (Ctrl+C) (0.4.0)
- [x] Errores de yt-dlp limpios, traducidos y mostrados una sola vez (0.4.0)
- [x] Carátula/metadatos/capítulos; carátula solo donde el formato la admite (0.4.0)
- [x] SponsorBlock, cookies del navegador y opciones `[ytdlp]` (0.4.0)
- [x] Políticas `skip`/`overwrite`/`rename` (rename con la misma lógica de nombres que yt-dlp, 0.4.0)
- [x] Configuración TOML validada (permisos 0600), perfiles gestionables por comando
- [x] Historial por video, `history --failed`, exportación JSON/CSV
- [x] Cache con TTL para `search` (0.4.0)
- [x] `doctor` con runtime JS, mutagen y antigüedad de yt-dlp (0.4.0)
- [x] `update`/`self-update` seguros frente a suplantación del nombre en PyPI (0.4.0)
- [x] Autocompletado bash/zsh/fish generado desde Typer (0.4.0) y página de manual
- [x] CI: ruff, ruff format, mypy strict, tests en 3.13 y 3.14, wheel, `makepkg` real (0.4.0)
- [x] Workflow de release con PyPI Trusted Publishing y attestations (0.4.0)

## Pendiente para 1.0

- [ ] **Publicar**: registrar `yt-cli` en PyPI (Trusted Publisher) y el paquete en AUR.
      Requiere las cuentas del mantenedor; los workflows ya están listos.
- [ ] **Verificar attestations (PEP 740) en `self-update`** antes de instalar.
- [ ] **Suite de integración real** (`@pytest.mark.integration`, ejecución semanal) con un
      video CC corto y una playlist de dos elementos con uno privado.
- [ ] **Historial en SQLite** cuando el volumen lo justifique (hoy `add_many` escribe una
      vez por ejecución; con decenas de miles de filas convendría migrar).
- [ ] **Metadatos de YouTube Music más ricos** (álbum, número de pista, carátula cuadrada).
- [ ] **Internacionalización** (gettext es/en). Los textos de ayuda propios de Typer/Click
      (`--help`, `--install-completion`) siguen en inglés.
- [ ] **`RENAME` para playlists/canales.**
- [ ] **Barra de progreso global** en colecciones (hoy se muestra la posición `n/N` en la
      barra del archivo actual).

## Fuera de alcance por ahora

TUI (Textual), scheduler, watch mode, sistema de plugins y soporte de otros sitios: son
decisiones de alto coste de mantenimiento que se aplazan hasta tener señales de uso real.
