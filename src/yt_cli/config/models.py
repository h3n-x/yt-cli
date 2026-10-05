"""Modelos de configuración validados con Pydantic.

La configuración se serializa/deserializa como TOML en
~/.config/yt-cli/config.toml (o $XDG_CONFIG_HOME/yt-cli/config.toml).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from yt_cli.models.enums import AudioFormat, AudioQuality, OverwritePolicy, VideoFormat, VideoQuality

DEFAULT_FILENAME_TEMPLATE = "{uploader}/{title}.{ext}"
DEFAULT_PLAYLIST_TEMPLATE = "{uploader}/{playlist}/{title}.{ext}"


class DownloadDefaults(BaseModel):
    """Valores por defecto aplicados cuando el usuario no pasa flags explícitos.

    También es el tipo usado para cada perfil con nombre en `AppConfig.profiles`.
    `validate_assignment=True` es necesario para que `yt-cli config profile set`
    pueda hacer `setattr(perfil, campo, valor_string)` y obtenga la misma
    coerción/validación de tipos que un campo de `[downloads]` normal (p. ej.
    convertir el string "flac" al enum `AudioFormat.FLAC`), en vez de guardar
    un string suelto sin validar.
    """

    model_config = {"validate_assignment": True}

    video_format: VideoFormat = VideoFormat.MP4
    audio_format: AudioFormat = AudioFormat.MP3
    video_quality: VideoQuality = VideoQuality.P1080
    audio_quality: AudioQuality = AudioQuality.K192
    filename_template: str = DEFAULT_FILENAME_TEMPLATE
    playlist_filename_template: str = DEFAULT_PLAYLIST_TEMPLATE
    overwrite_policy: OverwritePolicy = OverwritePolicy.SKIP
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    embed_chapters: bool = True
    download_subtitles: bool = False
    subtitle_languages: list[str] = Field(default_factory=lambda: ["en"])


class NetworkConfig(BaseModel):
    proxy: str | None = None
    max_concurrent_downloads: int = Field(default=3, ge=1, le=16)
    max_concurrent_fragments: int = Field(default=4, ge=1, le=32)
    retries: int = Field(default=10, ge=0, le=100)
    rate_limit_kbps: int | None = Field(default=None, ge=1)


class GeneralConfig(BaseModel):
    download_directory: Path = Field(default_factory=lambda: Path.home() / "Downloads" / "yt-cli")
    language: str = "es"
    check_for_updates: bool = True
    history_enabled: bool = True
    cache_enabled: bool = True
    cache_ttl_hours: int = Field(default=24, ge=0)

    @field_validator("download_directory", mode="before")
    @classmethod
    def _expand_path(cls, value: str | Path) -> Path:
        return Path(value).expanduser()


class AppConfig(BaseModel):
    """Raíz del árbol de configuración. Es lo que se serializa a config.toml."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    downloads: DownloadDefaults = Field(default_factory=DownloadDefaults)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    profiles: dict[str, DownloadDefaults] = Field(
        default_factory=dict,
        description=(
            "Perfiles con nombre que sobreescriben `downloads` por completo al "
            "usar `--profile <nombre>`. Ejemplo: [profiles.archivo] audio_format "
            "= 'flac', audio_quality = 'best'."
        ),
    )

    model_config = {"validate_assignment": True}

    def resolve_downloads(self, profile_name: str | None) -> DownloadDefaults:
        """Devuelve los valores de descarga por defecto a usar: los de un
        perfil con nombre si se pidió uno y existe, o los globales de
        `downloads` en caso contrario.
        """
        if profile_name is None:
            return self.downloads
        if profile_name not in self.profiles:
            available = ", ".join(sorted(self.profiles)) or "(ninguno definido)"
            raise KeyError(f"Perfil '{profile_name}' no existe. Perfiles disponibles: {available}")
        return self.profiles[profile_name]
