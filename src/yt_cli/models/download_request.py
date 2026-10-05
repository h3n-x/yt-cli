"""Modelo que representa una única solicitud de descarga, ya validada."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from yt_cli.core.validators import InvalidURLError, validate_url
from yt_cli.models.enums import (
    AudioFormat,
    AudioQuality,
    DownloadKind,
    OverwritePolicy,
    VideoFormat,
    VideoQuality,
)
from yt_cli.utils.naming import render_filename_template

# Contexto ficticio usado únicamente para validar que la plantilla es
# sintácticamente correcta (placeholders reconocidos) antes de iniciar una
# descarga. Los valores reales de {title}/{uploader}/etc. no se conocen hasta
# que yt-dlp extrae los metadatos, así que esta validación solo puede atrapar
# errores de sintaxis de la plantilla, no valores concretos.
_TEMPLATE_PROBE_CONTEXT = {
    "title": "probe",
    "uploader": "probe",
    "date": "probe",
    "id": "probe",
    "playlist": "probe",
    "resolution": "probe",
    "ext": "probe",
}


class DownloadRequest(BaseModel):
    url: str
    kind: DownloadKind
    output_directory: Path
    filename_template: str

    video_format: VideoFormat = VideoFormat.MP4
    audio_format: AudioFormat = AudioFormat.MP3
    video_quality: VideoQuality = VideoQuality.P1080
    audio_quality: AudioQuality = AudioQuality.K192

    overwrite_policy: OverwritePolicy = OverwritePolicy.SKIP
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    embed_chapters: bool = True
    download_subtitles: bool = False
    subtitle_languages: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        try:
            return validate_url(value)
        except InvalidURLError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("output_directory", mode="before")
    @classmethod
    def _expand_output_directory(cls, value: str | Path) -> Path:
        return Path(value).expanduser().resolve()

    @field_validator("filename_template")
    @classmethod
    def _validate_filename_template(cls, value: str) -> str:
        """Falla rápido (con un error de Pydantic legible) si la plantilla usa
        un placeholder no soportado, en vez de dejar que yt-dlp falle a mitad
        de la descarga con un error interno menos claro (corrige B5).
        """
        try:
            render_filename_template(value, _TEMPLATE_PROBE_CONTEXT)
        except ValueError as exc:
            raise ValueError(f"Plantilla de nombre de archivo inválida: {exc}") from exc
        return value
