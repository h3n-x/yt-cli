"""Modelo que representa una única solicitud de descarga, ya validada."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from yt_cli.models.enums import (
    AudioFormat,
    AudioQuality,
    DownloadKind,
    MediaType,
    OverwritePolicy,
    Scope,
    VideoFormat,
    VideoQuality,
)
from yt_cli.utils.naming import render_filename_template
from yt_cli.utils.validators import InvalidURLError, validate_url

# Contexto ficticio usado únicamente para validar que la plantilla es
# sintácticamente correcta (placeholders reconocidos) antes de iniciar una
# descarga. Los valores reales de {title}/{uploader}/etc. no se conocen hasta
# que yt-dlp extrae los metadatos.
_TEMPLATE_PROBE_CONTEXT = {
    "title": "probe",
    "uploader": "probe",
    "date": "probe",
    "id": "probe",
    "playlist": "probe",
    "resolution": "probe",
    "ext": "probe",
}

# Equivalencia del antiguo campo `kind` (< 0.4.0) con los ejes media/scope.
_LEGACY_KIND: dict[DownloadKind, tuple[MediaType, Scope]] = {
    DownloadKind.VIDEO: (MediaType.VIDEO, Scope.SINGLE),
    DownloadKind.AUDIO: (MediaType.AUDIO, Scope.SINGLE),
    DownloadKind.PLAYLIST: (MediaType.VIDEO, Scope.PLAYLIST),
    DownloadKind.CHANNEL: (MediaType.VIDEO, Scope.CHANNEL),
}


class DownloadRequest(BaseModel):
    url: str
    media: MediaType = MediaType.VIDEO
    scope: Scope = Scope.SINGLE
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

    # Rango de entradas de una colección, sintaxis de yt-dlp: "1:10", "1,3,5-7".
    playlist_items: str | None = None
    # Archivo de registro de yt-dlp: las entradas ya descargadas se saltan.
    download_archive: Path | None = None
    # Categorías de SponsorBlock a recortar (p. ej. ["sponsor", "selfpromo"]).
    sponsorblock_remove: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_kind(cls, data: Any) -> Any:
        """Acepta `kind=DownloadKind.X` (API anterior a 0.4.0) traduciéndolo a
        `media` + `scope`, para no romper código ni tests existentes.
        """
        if isinstance(data, dict) and "kind" in data:
            data = dict(data)
            media, scope = _LEGACY_KIND[DownloadKind(data.pop("kind"))]
            data.setdefault("media", media)
            data.setdefault("scope", scope)
        return data

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
        de la descarga con un error interno menos claro.
        """
        try:
            render_filename_template(value, _TEMPLATE_PROBE_CONTEXT)
        except ValueError as exc:
            raise ValueError(f"Plantilla de nombre de archivo inválida: {exc}") from exc
        return value

    @field_validator("playlist_items")
    @classmethod
    def _validate_playlist_items(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = set("0123456789:,-")
        if not value or not set(value) <= allowed:
            raise ValueError(
                f"Rango de entradas inválido: '{value}'. "
                "Ejemplos válidos: '1:10', '1,3,5-7', '-5:'."
            )
        return value

    @property
    def kind(self) -> DownloadKind:
        """Etiqueta resumida para el historial (ver `DownloadKind`)."""
        if self.scope is Scope.PLAYLIST:
            return DownloadKind.PLAYLIST
        if self.scope is Scope.CHANNEL:
            return DownloadKind.CHANNEL
        return DownloadKind.AUDIO if self.media is MediaType.AUDIO else DownloadKind.VIDEO

    @property
    def target_extension(self) -> str:
        """Extensión final del archivo tras el postprocesado."""
        return (self.audio_format if self.media is MediaType.AUDIO else self.video_format).value
