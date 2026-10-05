# yt-cli

Descargador multimedia profesional para YouTube, pensado para Linux (probado en Arch Linux).
Video, audio, playlists, canales, colas concurrentes, conversión con ffmpeg, historial y cache — con una UX cuidada al estilo `git`/`uv`/`cargo`/`gh`.

> **Estado del proyecto:** beta funcional (v0.3.0). Ver [ROADMAP.md](ROADMAP.md) para lo
> que falta antes de un 1.0 estable, y [CHANGELOG.md](CHANGELOG.md) para el detalle de
> cada versión.

> ## ⚠️ Siempre entre comillas las URLs
>
> Las URLs de YouTube casi siempre contienen `&`, `?` o `=`. **Si no las pones entre
> comillas, tu shell (zsh, bash) las interpreta a ELLAS, no yt-cli**, y falla antes de
> que el programa llegue a ejecutarse:
>
> ```bash
> # ❌ MAL — zsh interpreta '&' como "ejecutar en segundo plano" y '?' como un glob:
> yt-cli download https://youtu.be/abc123?list=XYZ&si=abc
> #   zsh: no matches found: https://youtu.be/abc123?list=XYZ
>
> # ✅ BIEN — la URL completa entre comillas dobles:
> yt-cli download "https://youtu.be/abc123?list=XYZ&si=abc"
> ```
>
> Esto no es un bug de yt-cli: ocurre en cualquier programa de línea de comandos con
> cualquier URL que contenga esos caracteres. `yt-cli doctor` te recuerda esta regla al
> final de su salida.

## Características

- Descarga de video (`mp4`, `mkv`, `webm`, `mov`) y audio (`mp3`, `ogg`, `opus`, `flac`, `wav`, `m4a`, `aac`)
- Calidad configurable: `144p`–`2160p` para video, `64k`–`320k` para audio, o `best`
- Playlists y canales completos, con reporte preciso de éxito parcial (no todo-o-nada)
- Descarga por lotes desde un archivo de URLs, con concurrencia configurable
- Reanudación automática, detección de archivos existentes y renombrado automático ante
  conflictos (`skip`/`overwrite`/`rename`)
- Rate limiting y reintentos con backoff exponencial acotado
- Perfiles de configuración con nombre (`--profile`) para alternar presets
- Embebido de miniatura, metadatos y capítulos; subtítulos opcionales
- Historial de descargas (exportable a JSON/CSV) y cache de metadatos con TTL
- Configuración persistente en TOML, validada con Pydantic
- Barra de progreso enriquecida (velocidad, ETA, tamaño) vía Rich
- Validación estricta de URLs y rutas; locking entre procesos para config/historial/cache
- Perfiles gestionables por comando (`config profile list/show/set/remove`), no solo edición manual del TOML
- `yt-cli update` / `yt-cli self-update` para comprobar e instalar nuevas versiones
- Salida `--json` en `search`, `history` y `version` para scripting
- `--version` como flag global (además del subcomando `version`)
- Respeta [`NO_COLOR`](https://no-color.org/) para accesibilidad

## Instalación

### Arch Linux (recomendado)

```bash
git clone https://github.com/yt-cli/yt-cli.git
cd yt-cli
makepkg -si -p packaging/PKGBUILD
```

O, una vez publicado en AUR:

```bash
yay -S yt-cli
# o
paru -S yt-cli
```

### Desde código fuente (cualquier distro con Python 3.13+)

```bash
git clone https://github.com/yt-cli/yt-cli.git
cd yt-cli
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Requiere `ffmpeg` y `ffprobe` instalados y en `PATH` (`sudo pacman -S ffmpeg`).

## Uso básico

```bash
# Descargar un video en 1080p (mp4 por defecto)
yt-cli download "https://www.youtube.com/watch?v=XXXXXXXXXXX"

# Descargar solo el audio en formato opus
yt-cli audio "https://youtu.be/XXXXXXXXXXX" --format opus --quality 320k

# Descargar una playlist completa
yt-cli playlist "https://www.youtube.com/playlist?list=XXXXXXXXXXX"

# Descargar un canal completo
yt-cli channel "https://www.youtube.com/@algun_canal"

# Descarga por lotes, con concurrencia definida en config.toml
yt-cli batch urls.txt

# Buscar y ver resultados antes de descargar
yt-cli search "lofi hip hop"

# Ver y modificar configuración
yt-cli config show
yt-cli config set downloads.video_quality 720p

# Diagnóstico del entorno (ffmpeg, permisos, etc.)
yt-cli doctor

# Historial y cache
yt-cli history
yt-cli history --json
yt-cli history export historial.json --format json
yt-cli history export historial.csv --format csv
yt-cli history clear
yt-cli cache stats

# Actualizaciones
yt-cli update              # solo comprueba si hay una versión nueva
yt-cli self-update          # comprueba e instala vía pip

# Perfiles (gestión completa por comando, no solo editando el TOML)
yt-cli config profile list
yt-cli config profile set archivo audio_format flac
yt-cli config profile show archivo
yt-cli config profile remove archivo

# Salida machine-readable para scripting
yt-cli search "lofi" --json
yt-cli version --json
```

Todos los comandos aceptan `--help`.

### Perfiles de configuración

Gestiónalos por comando:

```bash
yt-cli config profile set archivo audio_format flac
yt-cli config profile set archivo audio_quality best
yt-cli --profile archivo audio "https://youtu.be/XXXXXXXXXXX"
```

O edítalos directamente en `config.toml` (ver más abajo).

### Archivo de URLs para `batch`

```
# urls.txt — líneas que empiezan con # se ignoran
https://www.youtube.com/watch?v=aaaaaaaaaaa
https://www.youtube.com/watch?v=bbbbbbbbbbb
https://youtu.be/ccccccccccc
```

### Plantillas de nombre de archivo

Placeholders soportados: `{title}` `{uploader}` `{date}` `{id}` `{playlist}` `{resolution}` `{ext}`.

```bash
yt-cli download URL --template "{uploader}/{playlist}/{title}.{ext}"
```

Los nombres se sanitizan automáticamente para ser válidos en Linux, macOS y Windows.

## Configuración

Archivo: `~/.config/yt-cli/config.toml` (o `$XDG_CONFIG_HOME/yt-cli/config.toml`).

```toml
[general]
download_directory = "~/Downloads/yt-cli"
language = "es"
history_enabled = true
cache_enabled = true
cache_ttl_hours = 24

[downloads]
video_format = "mp4"
audio_format = "mp3"
video_quality = "1080p"
audio_quality = "192k"
filename_template = "{uploader}/{title}.{ext}"
overwrite_policy = "skip"
embed_thumbnail = true
embed_metadata = true
embed_chapters = true

[network]
max_concurrent_downloads = 3
max_concurrent_fragments = 4
retries = 10
proxy = ""
rate_limit_kbps = 500  # opcional; si se omite (o es null), no hay límite de velocidad

[profiles.archivo]
audio_format = "flac"
audio_quality = "best"

[profiles.rapido]
video_quality = "480p"
```

## Desarrollo

```bash
pip install -e ".[dev]"
ruff check .
mypy src/
pytest
```

Ver [ARCHITECTURE.md](ARCHITECTURE.md) para el diseño interno y
[CONTRIBUTING.md](CONTRIBUTING.md) para el flujo de contribución.

## Seguridad

Ver [SECURITY.md](SECURITY.md).

## Licencia

MIT. Ver [LICENSE](LICENSE).
