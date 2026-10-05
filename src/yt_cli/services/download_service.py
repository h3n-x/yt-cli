"""Capa de aplicación entre la CLI y el downloader.

Concentra lo que antes estaba repetido en cada comando de `cli/main.py`:
construir el downloader a partir de la configuración, preparar la solicitud
(alcance de la URL, archivo de descargas) y registrar el historial.
No sabe nada de Rich ni de Typer.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from platformdirs import user_data_dir

from yt_cli.config.models import AppConfig, DownloadDefaults
from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import (
    AudioFormat,
    AudioQuality,
    MediaType,
    Scope,
    VideoFormat,
    VideoQuality,
)
from yt_cli.models.results import DownloadResult
from yt_cli.services.history import HistoryEntry, HistoryStore
from yt_cli.utils.validators import detect_scope

if TYPE_CHECKING:
    from yt_cli.core.downloader import YtDlpDownloader


def download_archive_path() -> Path:
    return Path(user_data_dir("yt-cli", appauthor=False)) / "archive.txt"


def build_downloader(config: AppConfig) -> YtDlpDownloader:
    # Import diferido: yt-dlp tarda ~50 ms en importarse y solo lo necesitan
    # los comandos que descargan o consultan YouTube.
    from yt_cli.core.downloader import YtDlpDownloader

    return YtDlpDownloader(
        max_concurrent_fragments=config.network.max_concurrent_fragments,
        retries=config.network.retries,
        proxy=config.network.proxy or None,
        rate_limit_kbps=config.network.rate_limit_kbps,
        cookies_from_browser=config.network.cookies_from_browser,
        extra_options=config.ytdlp,
    )


def build_request(
    url: str,
    *,
    media: MediaType,
    config: AppConfig,
    defaults: DownloadDefaults,
    scope: Scope | None = None,
    output: Path | None = None,
    template: str | None = None,
    video_format: VideoFormat | None = None,
    audio_format: AudioFormat | None = None,
    video_quality: VideoQuality | None = None,
    audio_quality: AudioQuality | None = None,
    playlist_items: str | None = None,
    use_archive: bool | None = None,
) -> DownloadRequest:
    """Construye un `DownloadRequest` combinando flags, perfil y configuración.

    Si no se indica `scope`, se deduce de la URL: así `yt-cli audio <playlist>`
    descarga la playlist completa en audio, sin abortar ante el primer video
    no disponible. Lanza `ValueError`/`pydantic.ValidationError` si algo no es
    válido (URL, plantilla, rango).
    """
    from yt_cli.utils.validators import validate_url

    resolved_scope = scope or detect_scope(validate_url(url))
    if template is None:
        template = (
            defaults.playlist_filename_template
            if resolved_scope.is_collection
            else defaults.filename_template
        )
    archive_enabled = defaults.use_download_archive if use_archive is None else use_archive

    return DownloadRequest(
        url=url,
        media=media,
        scope=resolved_scope,
        output_directory=output or config.general.download_directory,
        filename_template=template,
        video_format=video_format or defaults.video_format,
        audio_format=audio_format or defaults.audio_format,
        video_quality=video_quality or defaults.video_quality,
        audio_quality=audio_quality or defaults.audio_quality,
        overwrite_policy=defaults.overwrite_policy,
        embed_thumbnail=defaults.embed_thumbnail,
        embed_metadata=defaults.embed_metadata,
        embed_chapters=defaults.embed_chapters,
        download_subtitles=defaults.download_subtitles,
        subtitle_languages=defaults.subtitle_languages,
        playlist_items=playlist_items,
        download_archive=download_archive_path() if archive_enabled else None,
        sponsorblock_remove=defaults.sponsorblock_remove,
    )


def record_history(config: AppConfig, results: list[DownloadResult]) -> None:
    """Registra en el historial una fila por video (o por descarga individual),
    con una sola escritura del archivo.
    """
    if not config.general.history_enabled:
        return
    rows = [row for result in results for row in HistoryEntry.rows_for(result)]
    HistoryStore().add_many(rows)
