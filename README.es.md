<h3 align="center">
  <img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/misc/transparent.png" height="30" width="0"/>
  yt-cli
  <img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/misc/transparent.png" height="30" width="0"/>
  <br/>
  <a href="https://github.com/h3n-x/yt-cli">Descargador de YouTube y YouTube Music para Linux, sobre la API Python de yt-dlp, con una UX al estilo git/uv/cargo/gh</a>
  <br/><br/>
  <p>
    🌐 <a href="README.md">English</a> · <strong>Español</strong>
  </p>
</h3>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13_%7C_3.14-74c7ec?style=for-the-badge&logo=python&logoColor=d9e0ee&labelColor=363a4f" alt="Python"/>
  <img src="https://img.shields.io/badge/yt--dlp-Python_API-f38ba8?style=for-the-badge&logo=youtube&logoColor=d9e0ee&labelColor=363a4f" alt="yt-dlp"/>
  <img src="https://img.shields.io/badge/CLI-Typer_%2B_Rich-cba6f7?style=for-the-badge&labelColor=363a4f" alt="CLI"/>
  <img src="https://img.shields.io/badge/Arch_Linux-PKGBUILD-89dceb?style=for-the-badge&logo=archlinux&logoColor=d9e0ee&labelColor=363a4f" alt="Arch Linux"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.4.0_beta-fab387?style=for-the-badge&labelColor=363a4f" alt="version"/>
  <img src="https://img.shields.io/badge/tests-pytest_%C2%B7_hypothesis-a6e3a1?style=for-the-badge&logo=pytest&logoColor=d9e0ee&labelColor=363a4f" alt="tests"/>
  <img src="https://img.shields.io/badge/typing-mypy-74c7ec?style=for-the-badge&labelColor=363a4f" alt="typing"/>
  <img src="https://img.shields.io/badge/license-MIT-a6e3a1?style=for-the-badge&labelColor=363a4f" alt="license"/>
</p>

<p align="center">
  <a href="#-instalación">Instalación</a>
  ·
  <a href="#%EF%B8%8F-uso">Uso</a>
  ·
  <a href="#%EF%B8%8F-configuración">Configuración</a>
  ·
  <a href="CHANGELOG.md">Changelog</a>
  ·
  <a href="LICENSE">Licencia</a>
</p>

&nbsp;

## 🪄 Acerca de

Un descargador de YouTube y YouTube Music para Linux (probado en Arch Linux), construido sobre la API Python de
[yt-dlp](https://github.com/yt-dlp/yt-dlp): video, audio, playlists, canales y descargas por lotes, con buenos valores por
defecto, errores explicados y una UX al estilo `git`, `uv`, `cargo` y `gh`.

> [!NOTE]
> **Estado:** beta (v0.4.0). Ver [CHANGELOG.md](CHANGELOG.md) y [ROADMAP.md](ROADMAP.md); la auditoría técnica que motivó esta
> versión está en [docs/AUDIT_2026-10.md](docs/AUDIT_2026-10.md).

> [!WARNING]
> **Siempre entre comillas las URLs.** Las URLs de YouTube contienen `&`, `?` o `=`, y sin comillas **tu shell** (zsh, bash)
> las interpreta antes de que yt-cli llegue a ejecutarse:
>
> ```bash
> yt-cli audio https://music.youtube.com/playlist?list=XYZ&si=abc    # ❌ zsh: no matches found
> yt-cli audio "https://music.youtube.com/playlist?list=XYZ&si=abc"  # ✅
> ```

&nbsp;

## ✨ Características

| | |
|---|---|
| 🎬 **Video y audio** | Video en `mp4`, `mkv`, `webm`, `mov`; audio en `mp3`, `opus`, `m4a`, `flac`, `ogg`, `wav`, `aac`. Calidad `144p`–`2160p` en video, `64k`–`320k` en audio, o `best`. |
| 📚 **Playlists, álbumes y canales** | Álbumes de YouTube Music y canales completos, en video o en audio. Un video no disponible no detiene el resto, y al final se lista qué falló y por qué. |
| 🔄 **Sincronización** | Rango de entradas (`--items 1:10`) y archivo de descargas (`--archive`) para sincronizar una playlist sin volver a bajar lo que ya tienes. |
| ⚡ **Por lotes** | Descargas concurrentes desde un archivo de URLs. |
| 🏷️ **Metadatos** | Carátula, metadatos y capítulos incrustados; subtítulos opcionales; recorte de segmentos con SponsorBlock. |
| 🍪 **Cookies del navegador** | Para videos con restricción de edad o verificación anti-bot. |
| 🩺 **Errores explicados** | Los errores de yt-dlp se traducen a una causa y una acción concreta; `doctor` comprueba ffmpeg, el runtime JavaScript que YouTube exige, mutagen y la antigüedad de yt-dlp. |
| ⚙️ **Configuración** | TOML validado, perfiles con nombre (`--profile`), opciones avanzadas de yt-dlp vía `[ytdlp]`. |
| 🗂️ **Historial y cache** | Historial por video (exportable a JSON o CSV) y cache de búsquedas con TTL. |
| 🧰 **Pensado para la shell** | Salida `--json` en `search`, `history` y `version`; respeta [`NO_COLOR`](https://no-color.org/); autocompletado para bash, zsh y fish; página de manual. |

&nbsp;

## 📦 Instalación

**Arch Linux:**

```bash
git clone https://github.com/h3n-x/yt-cli.git
cd yt-cli/packaging
makepkg -si
```

El paquete instala las dependencias de Arch (`yt-dlp` arrastra `deno` y `yt-dlp-ejs`, necesarios para YouTube), el
autocompletado y la página de manual (`man yt-cli`).

**Otras distribuciones (Python 3.13+):**

```bash
pipx install git+https://github.com/h3n-x/yt-cli.git
# o
uv tool install git+https://github.com/h3n-x/yt-cli.git
```

Además necesitas `ffmpeg` y un runtime JavaScript para yt-dlp (se recomienda [`deno`](https://deno.com/)). Comprueba el
entorno con `yt-cli doctor`.

&nbsp;

## ⌨️ Uso

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

# Buscar, diagnóstico e historial
yt-cli search "lofi hip hop"
yt-cli doctor
yt-cli history --failed               # solo lo que falló, con su causa
yt-cli history export historial.csv --format csv
```

Todos los comandos aceptan `--help`. `download` y `audio` detectan solos si la URL es un video, una playlist o un canal.

<details>
<summary><b>Códigos de salida, archivos de lotes y plantillas de nombre</b></summary>

| Código | Significado |
|---|---|
| 0 | Todo descargado |
| 1 | Error (la descarga o colección falló, configuración inválida…) |
| 2 | Uso incorrecto (opción desconocida, archivo inexistente…) |
| 3 | Colección completada parcialmente (algunas entradas fallaron) |
| 130 | Cancelado con Ctrl+C |

Un archivo para `batch`, donde las líneas que empiezan por `#` se ignoran:

```
# urls.txt
https://www.youtube.com/watch?v=aaaaaaaaaaa
https://music.youtube.com/playlist?list=PLxxxxxxxx
```

Placeholders del nombre de archivo: `{title}` `{uploader}` `{date}` `{id}` `{playlist}` `{resolution}` `{ext}`. Solo los `/` de la
propia plantilla crean subdirectorios; un `/` en un título no.

```bash
yt-cli audio URL --template "{uploader}/{playlist}/{title}.{ext}"
```

</details>

&nbsp;

## ⚙️ Configuración

`~/.config/yt-cli/config.toml` (o `$XDG_CONFIG_HOME/yt-cli/config.toml`), con permisos `0600`. Se modifica con
`yt-cli config set <sección>.<clave> <valor>` (`none` restablece el valor por defecto) o a mano.

```bash
yt-cli config set general.download_directory ~/Music
yt-cli config set downloads.sponsorblock_remove sponsor,selfpromo
yt-cli config set network.cookies_from_browser firefox
yt-cli config profile set archivo audio_format flac
yt-cli --profile archivo audio "https://youtu.be/XXXXXXXXXXX"
```

<details>
<summary><b>Un config.toml completo</b></summary>

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

</details>

&nbsp;

## 🔄 Actualizar

- Paquete de Arch: `git pull` y, dentro de `packaging/`, `makepkg -si`.
- pipx / uv: `pipx upgrade yt-cli` / `uv tool upgrade yt-cli`.
- `yt-cli update` comprueba si hay una versión nueva publicada. `yt-cli self-update` solo actúa si yt-cli se instaló con pip en
  un entorno propio y si el paquete de PyPI declara este repositorio como origen (ver [SECURITY.md](SECURITY.md)).

> [!TIP]
> Mantén también yt-dlp al día: YouTube cambia a menudo y una versión vieja es la causa más común de fallos (`yt-cli doctor`
> avisa).

&nbsp;

## 🛠️ Desarrollo

```bash
pip install -e . --group dev      # pip ≥ 25.1 (o: uv sync)
ruff check . && ruff format --check .
mypy src/
pytest
```

&nbsp;

## 📚 Documentación

| Recurso | Descripción |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Cómo está organizado el código |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Cómo contribuir |
| [FAQ.md](FAQ.md) | Preguntas frecuentes |
| [SECURITY.md](SECURITY.md) | Política de seguridad y `self-update` |
| [docs/yt-cli.1](docs/yt-cli.1) | Página de manual |
| [README.md](README.md) | Este readme en inglés |

> [!IMPORTANT]
> El usuario es responsable de cumplir los Términos de Servicio de YouTube y las leyes de derechos de autor de su jurisdicción.

&nbsp;

<p align="center">
  <img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/footers/gray0_ctp_on_line.svg?sanitize=true" alt=""/>
</p>

<p align="center">
  Copyright © 2026 <a href="https://github.com/h3n-x">h3n-x</a>
</p>

<p align="center">
  <a href="https://github.com/h3n-x/yt-cli/blob/main/LICENSE"><img src="https://img.shields.io/static/v1?style=for-the-badge&message=MIT&logoColor=d9e0ee&label=License&labelColor=363a4f&color=a6e3a1" alt="MIT License"/></a>
</p>
