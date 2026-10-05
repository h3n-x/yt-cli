# yt-cli

Descargador de YouTube y YouTube Music para Linux (probado en Arch Linux), construido
sobre la API Python de [yt-dlp](https://github.com/yt-dlp/yt-dlp): video, audio,
playlists, canales y descargas por lotes, con buenos valores por defecto, errores
explicados y una UX al estilo `git`/`uv`/`cargo`/`gh`.

> **Estado:** beta (v0.4.0). Ver [CHANGELOG.md](CHANGELOG.md) y [ROADMAP.md](ROADMAP.md).
> La auditoría técnica que motivó esta versión está en
> [docs/AUDIT_2026-10.md](docs/AUDIT_2026-10.md).

> ## ⚠️ Siempre entre comillas las URLs
>
> Las URLs de YouTube contienen `&`, `?` o `=`. Sin comillas, **tu shell** (zsh, bash)
> las interpreta antes de que yt-cli llegue a ejecutarse:
>
> ```bash
> yt-cli audio https://music.youtube.com/playlist?list=XYZ&si=abc    # ❌ zsh: no matches found
> yt-cli audio "https://music.youtube.com/playlist?list=XYZ&si=abc"  # ✅
> ```

## Características

- Video (`mp4`, `mkv`, `webm`, `mov`) y audio (`mp3`, `opus`, `m4a`, `flac`, `ogg`, `wav`, `aac`)
- Calidad `144p`–`2160p` para video, `64k`–`320k` para audio, o `best`
- **Playlists, álbumes de YouTube Music y canales en video o en audio**; un video no
  disponible no detiene el resto, y al final se lista qué falló y por qué
- Rango de entradas (`--items 1:10`) y **archivo de descargas** (`--archive`) para
  sincronizar una playlist sin volver a bajar lo que ya tienes
- Descarga por lotes concurrente desde un archivo de URLs
- Carátula, metadatos y capítulos incrustados; subtítulos opcionales; recorte de
  segmentos con SponsorBlock
- Cookies del navegador para videos con restricción de edad o verificación anti-bot
- Errores de yt-dlp traducidos a una causa y una acción concreta
- Perfiles de configuración con nombre (`--profile`)
- Historial por video (exportable a JSON/CSV) y cache de búsquedas con TTL
- Configuración TOML validada; opciones avanzadas de yt-dlp vía `[ytdlp]`
- `doctor` comprueba ffmpeg, el runtime JavaScript que YouTube exige, mutagen y la
  antigüedad de yt-dlp
- Salida `--json` en `search`, `history` y `version`; respeta [`NO_COLOR`](https://no-color.org/)
- Autocompletado para bash, zsh y fish; página de manual

## Instalación

### Arch Linux

```bash
git clone https://github.com/h3n-x/yt-cli.git
cd yt-cli/packaging
makepkg -si
```

El paquete instala las dependencias de Arch (`yt-dlp` arrastra `deno` y `yt-dlp-ejs`,
necesarios para YouTube), el autocompletado y la página de manual (`man yt-cli`).

### Otras distribuciones (Python 3.13+)

```bash
pipx install git+https://github.com/h3n-x/yt-cli.git
# o
uv tool install git+https://github.com/h3n-x/yt-cli.git
```

Además necesitas `ffmpeg` y un runtime JavaScript para yt-dlp (se recomienda
[`deno`](https://deno.com/)). Comprueba el entorno con `yt-cli doctor`.

## Uso

```bash
# Una playlist o un álbum de YouTube Music, en audio (opus, mejor calidad)
yt-cli audio "https://music.youtube.com/playlist?list=XXXXXXXX" -f opus -q best

# Lo mismo, de forma explícita y solo las 10 primeras pistas
yt-cli playlist "https://www.youtube.com/playlist?list=XXXXXXXX" --audio -f m4a --items 1:10

# Sincronizar: la segunda vez solo baja las pistas nuevas
yt-cli audio "https://music.youtube.com/playlist?list=XXXXXXXX" --archive

# Un video en 1080p (mp4 por defecto) o en otra calidad
yt-cli download "https://www.youtube.com/watch?v=XXXXXXXXXXX"
yt-cli download "https://youtu.be/XXXXXXXXXXX" -q 720p -f mkv

# Un canal completo, en video o solo audio
yt-cli channel "https://www.youtube.com/@algun_canal" --audio

# Por lotes (concurrencia en network.max_concurrent_downloads)
yt-cli batch urls.txt --audio

# Buscar
yt-cli search "lofi hip hop"

# Diagnóstico del entorno
yt-cli doctor

# Historial
yt-cli history
yt-cli history --failed               # solo lo que falló, con su causa
yt-cli history export historial.csv --format csv
```

Todos los comandos aceptan `--help`. `download` y `audio` detectan solos si la URL es un
video, una playlist o un canal.

### Códigos de salida

| Código | Significado |
|---|---|
| 0 | Todo descargado |
| 1 | Error (la descarga o colección falló, configuración inválida…) |
| 2 | Uso incorrecto (opción desconocida, archivo inexistente…) |
| 3 | Colección completada parcialmente (algunas entradas fallaron) |
| 130 | Cancelado con Ctrl+C |

### Archivo de URLs para `batch`

```
# urls.txt — las líneas que empiezan por # se ignoran
https://www.youtube.com/watch?v=aaaaaaaaaaa
https://music.youtube.com/playlist?list=PLxxxxxxxx
```

### Plantillas de nombre de archivo

Placeholders: `{title}` `{uploader}` `{date}` `{id}` `{playlist}` `{resolution}` `{ext}`.
Solo los `/` de la propia plantilla crean subdirectorios; un `/` en un título no.

```bash
yt-cli audio URL --template "{uploader}/{playlist}/{title}.{ext}"
```

## Configuración

Archivo: `~/.config/yt-cli/config.toml` (o `$XDG_CONFIG_HOME/yt-cli/config.toml`), con
permisos `0600`. Se modifica con `yt-cli config set <sección>.<clave> <valor>`
(`none` restablece el valor por defecto) o editándolo a mano.

```toml
[general]
download_directory = "~/Music"
history_enabled = true
cache_enabled = true         # cache de resultados de `search`
cache_ttl_hours = 24

[downloads]
video_format = "mp4"
audio_format = "opus"
video_quality = "1080p"
audio_quality = "best"
filename_template = "{uploader}/{title}.{ext}"
playlist_filename_template = "{uploader}/{playlist}/{title}.{ext}"
overwrite_policy = "skip"    # skip | overwrite | rename
embed_thumbnail = true
embed_metadata = true
embed_chapters = true
use_download_archive = false # true = como pasar siempre --archive
sponsorblock_remove = []     # p. ej. ["sponsor", "selfpromo"]

[network]
max_concurrent_downloads = 3
max_concurrent_fragments = 4
retries = 10
# proxy = "http://usuario:pass@host:3128"   # se oculta en `config show`
# rate_limit_kbps = 500
# cookies_from_browser = "firefox"          # o "chrome:Perfil 1"

[profiles.archivo]
audio_format = "flac"
audio_quality = "best"

# Opciones adicionales de yt_dlp.YoutubeDL (nombres de la API de Python).
# Las que yt-cli gestiona internamente (formato, rutas, progreso…) se ignoran.
[ytdlp]
geo_bypass_country = "ES"
```

```bash
yt-cli config set general.download_directory ~/Music
yt-cli config set downloads.sponsorblock_remove sponsor,selfpromo
yt-cli config set network.cookies_from_browser firefox
yt-cli config profile set archivo audio_format flac
yt-cli --profile archivo audio "https://youtu.be/XXXXXXXXXXX"
```

## Actualizar

- Paquete de Arch: `git pull` y, dentro de `packaging/`, `makepkg -si`.
- pipx/uv: `pipx upgrade yt-cli` / `uv tool upgrade yt-cli`.
- `yt-cli update` comprueba si hay una versión nueva publicada. `yt-cli self-update` solo
  actúa si yt-cli se instaló con pip en un entorno propio y si el paquete de PyPI declara
  este repositorio como origen (ver [SECURITY.md](SECURITY.md)).

Mantén también yt-dlp al día: YouTube cambia a menudo y una versión vieja es la causa
más común de fallos (`yt-cli doctor` avisa).

## Desarrollo

```bash
pip install -e . --group dev      # pip ≥ 25.1 (o: uv sync)
ruff check . && ruff format --check .
mypy src/
pytest
```

Ver [ARCHITECTURE.md](ARCHITECTURE.md) y [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

MIT. Ver [LICENSE](LICENSE). El usuario es responsable de cumplir los Términos de
Servicio de YouTube y las leyes de derechos de autor de su jurisdicción.
