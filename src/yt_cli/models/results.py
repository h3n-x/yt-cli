"""Resultados y eventos de descarga, agnósticos de yt-dlp y de la UI.

Viven en `models/` (y no en `core/downloader.py`) para que la capa de
presentación (`utils/progress_ui.py`) y los servicios puedan usarlos sin
importar yt-dlp, respetando la regla de dependencias de ARCHITECTURE.md.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import DownloadStatus


@dataclass(slots=True)
class ProgressEvent:
    """Evento de progreso normalizado para la capa de UI."""

    status: DownloadStatus
    filename: str | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed_bps: float | None = None
    eta_seconds: int | None = None
    percent: float | None = None
    # Posición dentro de una colección (1-based) y tamaño total, si aplica.
    playlist_index: int | None = None
    playlist_count: int | None = None


@dataclass(slots=True)
class EntryResult:
    """Resultado de una entrada individual dentro de una playlist/canal."""

    status: DownloadStatus
    title: str | None
    url: str | None
    output_path: Path | None
    error_message: str | None = None


@dataclass(slots=True)
class DownloadResult:
    request: DownloadRequest
    status: DownloadStatus
    output_path: Path | None
    title: str | None
    error_message: str | None = None
    # Solo para colecciones: permite distinguir "completado" de "parcial".
    entry_count: int | None = None
    entry_failures: int | None = None
    entries: list[EntryResult] = field(default_factory=list)


ProgressCallback = Callable[[ProgressEvent], None]
