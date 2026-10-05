"""Detección de dependencias externas de las que depende una descarga real.

yt-dlp no falla al importarse si falta alguna de estas piezas; falla más tarde,
a mitad de una descarga y con un mensaje poco claro. Este módulo permite
comprobarlas por adelantado (en `doctor` y antes de descargar).
"""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass
from datetime import date

# Runtimes JavaScript soportados por yt-dlp para resolver los retos de YouTube
# (obligatorio desde yt-dlp 2025.11.12). Deno es el recomendado y el que
# yt-dlp habilita por defecto; el binario de QuickJS se llama `qjs`.
JS_RUNTIME_BINARIES = ("deno", "node", "bun", "qjs")

# Formatos de audio cuyo embebido de miniatura requiere el módulo `mutagen`
# (yt_dlp/postprocessor/embedthumbnail.py); mp3/m4a usan ffmpeg.
MUTAGEN_THUMBNAIL_FORMATS = frozenset({"ogg", "opus", "flac"})

# A partir de esta antigüedad se recomienda actualizar yt-dlp: YouTube cambia
# con frecuencia y una versión vieja es la causa más común de fallos.
STALE_YT_DLP_DAYS = 90


class FFmpegNotFoundError(RuntimeError):
    """ffmpeg o ffprobe no están instalados / no están en PATH."""


@dataclass(frozen=True, slots=True)
class YtDlpVersionInfo:
    version: str
    release_date: date | None
    age_days: int | None


def require_ffmpeg() -> None:
    """Lanza `FFmpegNotFoundError` si falta ffmpeg o ffprobe."""
    for name in ("ffmpeg", "ffprobe"):
        if shutil.which(name) is None:
            raise FFmpegNotFoundError(
                f"'{name}' no se encontró en PATH. Instálalo con: sudo pacman -S ffmpeg"
            )


def find_js_runtime() -> str | None:
    """Devuelve el nombre del primer runtime JS disponible, o None."""
    for binary in JS_RUNTIME_BINARIES:
        if shutil.which(binary) is not None:
            return binary
    return None


def has_mutagen() -> bool:
    return importlib.util.find_spec("mutagen") is not None


def yt_dlp_version_info(today: date | None = None) -> YtDlpVersionInfo | None:
    """Versión instalada de yt-dlp y su antigüedad (sus versiones son fechas
    `AAAA.MM.DD[.n]`). Devuelve None si yt-dlp no está instalado.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        raw = version("yt-dlp")
    except PackageNotFoundError:
        return None

    try:
        year, month, day = (int(part) for part in raw.split(".")[:3])
        released: date | None = date(year, month, day)
    except ValueError:
        released = None

    age = ((today or date.today()) - released).days if released else None
    return YtDlpVersionInfo(version=raw, release_date=released, age_days=age)
