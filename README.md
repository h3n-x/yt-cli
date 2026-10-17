<h3 align="center">
  <img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/misc/transparent.png" height="30" width="0"/>
  yt-cli
  <img src="https://raw.githubusercontent.com/catppuccin/catppuccin/main/assets/misc/transparent.png" height="30" width="0"/>
  <br/>
  <a href="https://github.com/h3n-x/yt-cli">YouTube and YouTube Music downloader for Linux, built on yt-dlp's Python API, with a git/uv/cargo/gh-style UX</a>
  <br/><br/>
  <p>
    🌐 <strong>English</strong> · <a href="README.es.md">Español</a>
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
  <a href="#-install">Install</a>
  ·
  <a href="#%EF%B8%8F-usage">Usage</a>
  ·
  <a href="#%EF%B8%8F-configuration">Configuration</a>
  ·
  <a href="CHANGELOG.md">Changelog</a>
  ·
  <a href="LICENSE">License</a>
</p>

&nbsp;

## 🪄 About

A YouTube and YouTube Music downloader for Linux (tested on Arch Linux), built on the Python API of
[yt-dlp](https://github.com/yt-dlp/yt-dlp): video, audio, playlists, channels and batch downloads, with good defaults,
explained errors and a UX in the style of `git`, `uv`, `cargo` and `gh`.

> [!NOTE]
> **Status:** beta (v0.4.0). See [CHANGELOG.md](CHANGELOG.md) and [ROADMAP.md](ROADMAP.md); the technical audit behind this
> release is in [docs/AUDIT_2026-10.md](docs/AUDIT_2026-10.md).

> [!WARNING]
> **Always quote URLs.** YouTube URLs contain `&`, `?` or `=`, and without quotes **your shell** (zsh, bash) interprets them
> before yt-cli even runs:
>
> ```bash
> yt-cli audio https://music.youtube.com/playlist?list=XYZ&si=abc    # ❌ zsh: no matches found
> yt-cli audio "https://music.youtube.com/playlist?list=XYZ&si=abc"  # ✅
> ```

&nbsp;

## ✨ Features

| | |
|---|---|
| 🎬 **Video and audio** | Video in `mp4`, `mkv`, `webm`, `mov`; audio in `mp3`, `opus`, `m4a`, `flac`, `ogg`, `wav`, `aac`. Quality `144p`–`2160p` for video, `64k`–`320k` for audio, or `best`. |
| 📚 **Playlists, albums and channels** | YouTube Music albums and whole channels, as video or audio. An unavailable video doesn't stop the rest, and at the end you get what failed and why. |
| 🔄 **Sync** | Entry ranges (`--items 1:10`) and a download archive (`--archive`) to sync a playlist without fetching what you already have. |
| ⚡ **Batch** | Concurrent downloads from a file of URLs. |
| 🏷️ **Metadata** | Cover art, metadata and chapters embedded; optional subtitles; SponsorBlock segment removal. |
| 🍪 **Browser cookies** | For age-restricted videos or anti-bot checks. |
| 🩺 **Explained errors** | yt-dlp errors translated into a cause and a concrete action; `doctor` checks ffmpeg, the JavaScript runtime YouTube requires, mutagen and how old yt-dlp is. |
| ⚙️ **Configuration** | Validated TOML, named profiles (`--profile`), advanced yt-dlp options through `[ytdlp]`. |
| 🗂️ **History and cache** | Per-video history (exportable to JSON or CSV) and a search cache with a TTL. |
| 🧰 **Shell-friendly** | `--json` output in `search`, `history` and `version`; respects [`NO_COLOR`](https://no-color.org/); completion for bash, zsh and fish; a man page. |

&nbsp;

## 📦 Install

**Arch Linux:**

```bash
git clone https://github.com/h3n-x/yt-cli.git
cd yt-cli/packaging
makepkg -si
```

The package installs the Arch dependencies (`yt-dlp` pulls in `deno` and `yt-dlp-ejs`, which YouTube needs), the completions
and the man page (`man yt-cli`).

**Other distributions (Python 3.13+):**

```bash
pipx install git+https://github.com/h3n-x/yt-cli.git
# or
uv tool install git+https://github.com/h3n-x/yt-cli.git
```

You also need `ffmpeg` and a JavaScript runtime for yt-dlp ([`deno`](https://deno.com/) is recommended). Check the
environment with `yt-cli doctor`.

&nbsp;

## ⌨️ Usage

```bash
# A playlist or a YouTube Music album, as audio (opus, best quality)
yt-cli audio "https://music.youtube.com/playlist?list=XXXXXXXX" -f opus -q best

# The same, explicitly, and only the first 10 tracks
yt-cli playlist "https://www.youtube.com/playlist?list=XXXXXXXX" --audio -f m4a --items 1:10

# Sync: the second time only the new tracks are downloaded
yt-cli audio "https://music.youtube.com/playlist?list=XXXXXXXX" --archive

# A video in 1080p (mp4 by default), or another quality
yt-cli download "https://www.youtube.com/watch?v=XXXXXXXXXXX"
yt-cli download "https://youtu.be/XXXXXXXXXXX" -q 720p -f mkv

# A whole channel, as video or audio only
yt-cli channel "https://www.youtube.com/@some_channel" --audio

# Batch (concurrency in network.max_concurrent_downloads)
yt-cli batch urls.txt --audio

# Search, diagnostics and history
yt-cli search "lofi hip hop"
yt-cli doctor
yt-cli history --failed               # only what failed, with its cause
yt-cli history export history.csv --format csv
```

Every command accepts `--help`. `download` and `audio` detect on their own whether the URL is a video, a playlist or a
channel.

<details>
<summary><b>Exit codes, batch files and filename templates</b></summary>

| Code | Meaning |
|---|---|
| 0 | Everything downloaded |
| 1 | Error (the download or collection failed, invalid configuration…) |
| 2 | Wrong usage (unknown option, missing file…) |
| 3 | Collection partially completed (some entries failed) |
| 130 | Cancelled with Ctrl+C |

A file for `batch`, where lines starting with `#` are ignored:

```
# urls.txt
https://www.youtube.com/watch?v=aaaaaaaaaaa
https://music.youtube.com/playlist?list=PLxxxxxxxx
```

Filename placeholders: `{title}` `{uploader}` `{date}` `{id}` `{playlist}` `{resolution}` `{ext}`. Only the template's own `/`
create subdirectories; a `/` inside a title doesn't.

```bash
yt-cli audio URL --template "{uploader}/{playlist}/{title}.{ext}"
```

</details>

&nbsp;

## ⚙️ Configuration

`~/.config/yt-cli/config.toml` (or `$XDG_CONFIG_HOME/yt-cli/config.toml`), with `0600` permissions. Change it with
`yt-cli config set <section>.<key> <value>` (`none` restores the default) or by hand.

```bash
yt-cli config set general.download_directory ~/Music
yt-cli config set downloads.sponsorblock_remove sponsor,selfpromo
yt-cli config set network.cookies_from_browser firefox
yt-cli config profile set archive audio_format flac
yt-cli --profile archive audio "https://youtu.be/XXXXXXXXXXX"
```

<details>
<summary><b>A complete config.toml</b></summary>

```toml
[general]
download_directory = "~/Music"
history_enabled = true
cache_enabled = true         # cache for `search` results
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
use_download_archive = false # true = always behave as with --archive
sponsorblock_remove = []     # e.g. ["sponsor", "selfpromo"]

[network]
max_concurrent_downloads = 3
max_concurrent_fragments = 4
retries = 10
# proxy = "http://user:pass@host:3128"      # hidden in `config show`
# rate_limit_kbps = 500
# cookies_from_browser = "firefox"          # or "chrome:Profile 1"

[profiles.archive]
audio_format = "flac"
audio_quality = "best"

# Extra yt_dlp.YoutubeDL options (Python API names).
# The ones yt-cli manages itself (format, paths, progress…) are ignored.
[ytdlp]
geo_bypass_country = "ES"
```

</details>

&nbsp;

## 🔄 Update

- Arch package: `git pull`, then `makepkg -si` inside `packaging/`.
- pipx / uv: `pipx upgrade yt-cli` / `uv tool upgrade yt-cli`.
- `yt-cli update` checks whether a new version is published. `yt-cli self-update` only acts if yt-cli was installed with pip
  in its own environment and the PyPI package declares this repository as its source (see [SECURITY.md](SECURITY.md)).

> [!TIP]
> Keep yt-dlp up to date too: YouTube changes often, and an old yt-dlp is the most common cause of failures
> (`yt-cli doctor` warns about it).

&nbsp;

## 🛠️ Development

```bash
pip install -e . --group dev      # pip ≥ 25.1 (or: uv sync)
ruff check . && ruff format --check .
mypy src/
pytest
```

&nbsp;

## 📚 Documentation

| Resource | Description |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the code is organized |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [FAQ.md](FAQ.md) | Frequent questions |
| [SECURITY.md](SECURITY.md) | Security policy and `self-update` |
| [docs/yt-cli.1](docs/yt-cli.1) | Man page |
| [README.es.md](README.es.md) | This readme in Spanish |

> [!IMPORTANT]
> You are responsible for complying with YouTube's Terms of Service and the copyright law of your jurisdiction.

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
