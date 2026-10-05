"""Enumeraciones tipadas usadas en todo el proyecto.

Se usan `StrEnum` (Python 3.11+) para que los valores sean directamente
serializables a TOML/JSON y comparables como strings sin conversión manual.
"""

from __future__ import annotations

from enum import StrEnum


class VideoFormat(StrEnum):
    MP4 = "mp4"
    MKV = "mkv"
    WEBM = "webm"
    MOV = "mov"


class AudioFormat(StrEnum):
    MP3 = "mp3"
    OGG = "ogg"
    OPUS = "opus"
    FLAC = "flac"
    WAV = "wav"
    M4A = "m4a"
    AAC = "aac"


class VideoQuality(StrEnum):
    P144 = "144p"
    P240 = "240p"
    P360 = "360p"
    P480 = "480p"
    P720 = "720p"
    P1080 = "1080p"
    P1440 = "1440p"
    P2160 = "2160p"
    BEST = "best"

    @property
    def height(self) -> int | None:
        """Altura en píxeles, o None si es 'best' (sin límite)."""
        if self is VideoQuality.BEST:
            return None
        return int(self.value.removesuffix("p"))

    def as_yt_dlp_format(self) -> str:
        """Traduce la calidad a una expresión de selección de formato de yt-dlp."""
        if self is VideoQuality.BEST:
            return "bestvideo*+bestaudio/best"
        return f"bestvideo*[height<={self.height}]+bestaudio/best[height<={self.height}]"


class AudioQuality(StrEnum):
    K64 = "64k"
    K96 = "96k"
    K128 = "128k"
    K192 = "192k"
    K256 = "256k"
    K320 = "320k"
    BEST = "best"

    @property
    def kbps(self) -> int | None:
        if self is AudioQuality.BEST:
            return None
        return int(self.value.removesuffix("k"))


class MediaType(StrEnum):
    """Qué se descarga: video completo o solo la pista de audio."""

    VIDEO = "video"
    AUDIO = "audio"


class Scope(StrEnum):
    """Cuántos elementos abarca la URL: un único video o una colección."""

    SINGLE = "single"
    PLAYLIST = "playlist"
    CHANNEL = "channel"

    @property
    def is_collection(self) -> bool:
        return self is not Scope.SINGLE


class DownloadKind(StrEnum):
    """Etiqueta resumida (media + alcance) que se guarda en el historial.

    Se conserva por compatibilidad con `history.json` de versiones < 0.4.0;
    el dominio usa `MediaType` y `Scope`, que son ejes independientes (una
    playlist puede descargarse como video o como audio).
    """

    VIDEO = "video"
    AUDIO = "audio"
    PLAYLIST = "playlist"
    CHANNEL = "channel"


class OverwritePolicy(StrEnum):
    SKIP = "skip"  # No descargar si el archivo destino ya existe
    OVERWRITE = "overwrite"  # Sobrescribir siempre
    RENAME = "rename"  # Añadir sufijo numérico si existe


class DownloadStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    COMPLETED = "completed"
    PARTIAL = "partial"  # playlist/canal: algunas entradas OK, otras fallaron
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
