"""Wrapper sobre la API Python de yt-dlp (no la CLI de yt-dlp).

Se usa deliberadamente `yt_dlp.YoutubeDL` como librería en vez de invocar el
binario `yt-dlp` como subproceso: esto evita construir comandos por
concatenación de strings (fuente típica de command injection) y permite
recibir progreso estructurado vía hooks en vez de parsear stdout.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp

from yt_cli.core.validators import resolve_safe_path
from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import DownloadKind, DownloadStatus, OverwritePolicy
from yt_cli.utils.naming import render_filename_template

logger = logging.getLogger("yt_cli.downloader")

# Backoff exponencial acotado para reintentos de red ("reintentos inteligentes").
# yt-dlp, sin configurar `retry_sleep_functions`, reintenta inmediatamente sin
# pausa alguna entre intentos — lo que puede martillar un servidor que ya está
# devolviendo errores transitorios (5xx, timeouts). Se acota el techo (60s
# para HTTP, 30s para fragmentos) para no bloquear indefinidamente una
# descarga ante un fallo persistente.
_RETRY_SLEEP_FUNCTIONS: dict[str, Callable[[int], float]] = {
    "http": lambda n: min(4 * (2**n), 60),
    "fragment": lambda n: min(2 * (2**n), 30),
    "file_access": lambda n: min(1 * (2**n), 10),
}


@dataclass(slots=True)
class ProgressEvent:
    """Evento de progreso normalizado, agnóstico de yt-dlp, para la capa de UI."""

    status: DownloadStatus
    filename: str | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    speed_bps: float | None = None
    eta_seconds: int | None = None
    percent: float | None = None


@dataclass(slots=True)
class DownloadResult:
    request: DownloadRequest
    status: DownloadStatus
    output_path: Path | None
    title: str | None
    error_message: str | None = None
    # Solo poblado para DownloadKind.PLAYLIST / CHANNEL: permite distinguir
    # "completado" de "parcialmente completado" en vez de reportar siempre
    # COMPLETED aunque hayan fallado entradas individuales (corrige B4).
    entry_count: int | None = None
    entry_failures: int | None = None


ProgressCallback = Callable[[ProgressEvent], None]


class DownloadError(RuntimeError):
    """Fallo irrecuperable durante una descarga."""


def _build_output_template(request: DownloadRequest) -> str:
    """Traduce la plantilla propia de yt-cli ({title}, {uploader}, ...) al
    formato de outtmpl que espera yt-dlp (%(title)s, %(uploader)s, ...).
    """
    mapping = {
        "{title}": "%(title)s",
        "{uploader}": "%(uploader)s",
        "{date}": "%(upload_date)s",
        "{id}": "%(id)s",
        "{playlist}": "%(playlist_title)s",
        "{resolution}": "%(height)sp",
        "{ext}": "%(ext)s",
    }
    template = request.filename_template
    for placeholder, yt_dlp_field in mapping.items():
        template = template.replace(placeholder, yt_dlp_field)
    return str(request.output_directory / template)


def _build_postprocessors(request: DownloadRequest) -> list[dict[str, Any]]:
    postprocessors: list[dict[str, Any]] = []

    if request.kind is DownloadKind.AUDIO:
        preferred_quality = (
            "0" if request.audio_quality.value == "best" else str(request.audio_quality.kbps)
        )
        postprocessors.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": request.audio_format.value,
                "preferredquality": preferred_quality,
            }
        )
    else:
        postprocessors.append(
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": request.video_format.value,
            }
        )

    if request.embed_thumbnail:
        postprocessors.append({"key": "EmbedThumbnail"})
    if request.embed_metadata:
        postprocessors.append({"key": "FFmpegMetadata", "add_chapters": request.embed_chapters})
    if request.download_subtitles:
        postprocessors.append({"key": "FFmpegEmbedSubtitle"})

    return postprocessors


def _map_yt_dlp_progress(data: dict[str, Any]) -> ProgressEvent:
    status_map = {
        "downloading": DownloadStatus.DOWNLOADING,
        "finished": DownloadStatus.CONVERTING,
        "error": DownloadStatus.FAILED,
    }
    total = data.get("total_bytes") or data.get("total_bytes_estimate")
    downloaded = data.get("downloaded_bytes")
    percent = (downloaded / total * 100) if total and downloaded is not None else None

    return ProgressEvent(
        status=status_map.get(data.get("status", ""), DownloadStatus.DOWNLOADING),
        filename=data.get("filename"),
        downloaded_bytes=downloaded,
        total_bytes=total,
        speed_bps=data.get("speed"),
        eta_seconds=data.get("eta"),
        percent=percent,
    )


class YtDlpDownloader:
    """Ejecuta descargas individuales usando la API de yt-dlp."""

    def __init__(
        self,
        *,
        max_concurrent_fragments: int = 4,
        retries: int = 10,
        proxy: str | None = None,
        rate_limit_kbps: int | None = None,
    ):
        self._max_concurrent_fragments = max_concurrent_fragments
        self._retries = retries
        self._proxy = proxy
        self._rate_limit_kbps = rate_limit_kbps

    def _build_ydl_opts(
        self, request: DownloadRequest, progress_callback: ProgressCallback | None
    ) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "outtmpl": _build_output_template(request),
            "format": (
                "bestaudio/best"
                if request.kind is DownloadKind.AUDIO
                else request.video_quality.as_yt_dlp_format()
            ),
            "postprocessors": _build_postprocessors(request),
            "noplaylist": request.kind not in (DownloadKind.PLAYLIST, DownloadKind.CHANNEL),
            "concurrent_fragment_downloads": self._max_concurrent_fragments,
            "retries": self._retries,
            "fragment_retries": self._retries,
            "continuedl": True,  # reanudación automática
            "nopart": False,
            # "overwrites": False hace que yt-dlp omita la redescarga si el
            # archivo ya existe en la ruta templada; cubre la política SKIP
            # sin necesidad de una clave adicional (se retiró la clave
            # "nooverwrites", que no existe en yt_dlp.YoutubeDL — B1).
            "overwrites": request.overwrite_policy is OverwritePolicy.OVERWRITE,
            "ignoreerrors": request.kind in (DownloadKind.PLAYLIST, DownloadKind.CHANNEL),
            "writethumbnail": request.embed_thumbnail,
            "writesubtitles": request.download_subtitles,
            "subtitleslangs": request.subtitle_languages or ["en"],
            "retry_sleep_functions": _RETRY_SLEEP_FUNCTIONS,
            "quiet": True,
            "no_warnings": True,
            "logger": logging.getLogger("yt_dlp"),
        }

        if self._proxy:
            opts["proxy"] = self._proxy

        if self._rate_limit_kbps:
            # yt-dlp espera bytes/segundo; la configuración del usuario está en kbps.
            opts["ratelimit"] = self._rate_limit_kbps * 1024

        if progress_callback is not None:

            def _hook(data: dict[str, Any]) -> None:
                progress_callback(_map_yt_dlp_progress(data))

            opts["progress_hooks"] = [_hook]

        return opts

    def _resolve_rename_target(self, request: DownloadRequest) -> str | None:
        """Para overwrite_policy=RENAME: extrae metadatos sin descargar, calcula
        el nombre de archivo final con `naming.render_filename_template` (usando
        los metadatos reales del video) y, si ya existe un archivo en esa ruta,
        agrega un sufijo numérico ' (n)' hasta encontrar una ruta libre.

        Devuelve un `outtmpl` literal (ya resuelto) a usar en vez del template
        dinámico de yt-dlp, o `None` si no se pudo determinar (se procede sin
        renombrar, degradando a comportamiento por defecto en vez de fallar).

        Nota de alcance (ver ROADMAP.md): esto solo aplica a descargas
        individuales (video/audio), no a playlists/canales — resolver
        conflictos de nombre por entrada dentro de una colección requeriría
        una extracción de metadatos por cada entrada, lo cual es costoso en
        latencia y se deja fuera de esta iteración.
        """
        try:
            info = self.extract_metadata_only(request.url)
        except DownloadError:
            return None

        ext = request.audio_format.value if request.kind is DownloadKind.AUDIO else request.video_format.value
        context = {
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "date": info.get("upload_date"),
            "id": info.get("id"),
            "playlist": info.get("playlist_title"),
            "resolution": f"{info['height']}p" if info.get("height") else None,
            "ext": ext,
        }

        try:
            rendered_relative = render_filename_template(request.filename_template, context)
            target = resolve_safe_path(request.output_directory, rendered_relative)
        except ValueError:
            return None

        if not target.exists():
            return str(target)

        stem, suffix = target.stem, target.suffix
        counter = 1
        while True:
            candidate = target.with_name(f"{stem} ({counter}){suffix}")
            if not candidate.exists():
                return str(candidate)
            counter += 1

    def download(
        self, request: DownloadRequest, progress_callback: ProgressCallback | None = None
    ) -> DownloadResult:
        opts = self._build_ydl_opts(request, progress_callback)

        if request.overwrite_policy is OverwritePolicy.RENAME and request.kind in (
            DownloadKind.VIDEO,
            DownloadKind.AUDIO,
        ):
            resolved_outtmpl = self._resolve_rename_target(request)
            if resolved_outtmpl is not None:
                opts["outtmpl"] = resolved_outtmpl
                opts["overwrites"] = True  # ya elegimos una ruta libre; no hay nada que "saltar"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            logger.error("Fallo al descargar %s: %s", request.url, exc)
            return DownloadResult(
                request=request,
                status=DownloadStatus.FAILED,
                output_path=None,
                title=None,
                error_message=str(exc),
            )

        if info is None:
            return DownloadResult(
                request=request,
                status=DownloadStatus.FAILED,
                output_path=None,
                title=None,
                error_message="yt-dlp no devolvió metadatos para esta URL.",
            )

        if request.kind in (DownloadKind.PLAYLIST, DownloadKind.CHANNEL):
            # `download()` solo devuelve el resumen agregado; para obtener un
            # DownloadResult por cada entrada (usado por el historial) hay que
            # llamar a `download_collection()`, que hace la misma extracción
            # una única vez y devuelve ambas cosas.
            return self._summarize_collection_result(request, info)

        # 'requested_downloads' contiene la ruta final tras postprocesado.
        requested = info.get("requested_downloads") or []
        final_path = Path(requested[0]["filepath"]) if requested else None

        return DownloadResult(
            request=request,
            status=DownloadStatus.COMPLETED,
            output_path=final_path,
            title=info.get("title"),
        )

    def _summarize_collection_result(self, request: DownloadRequest, info: dict[str, Any]) -> DownloadResult:
        """Inspecciona `info['entries']` de una playlist/canal y reporta con
        precisión cuántas entradas se completaron vs. fallaron, en vez de
        asumir siempre COMPLETED (corrige B4).
        """
        entries = list(info.get("entries") or [])

        if not entries:
            # La URL resolvió a un único video (p. ej. un canal con un solo
            # video público), no a una colección: se trata como éxito simple.
            requested = info.get("requested_downloads") or []
            final_path = Path(requested[0]["filepath"]) if requested else None
            return DownloadResult(
                request=request,
                status=DownloadStatus.COMPLETED if requested else DownloadStatus.FAILED,
                output_path=final_path,
                title=info.get("title"),
                entry_count=1,
                entry_failures=0 if requested else 1,
            )

        failures = 0
        for entry in entries:
            if entry is None or not (entry.get("requested_downloads") or []):
                failures += 1

        total = len(entries)
        if failures == 0:
            status = DownloadStatus.COMPLETED
        elif failures == total:
            status = DownloadStatus.FAILED
        else:
            status = DownloadStatus.PARTIAL

        error_message = None
        if failures:
            error_message = f"{failures}/{total} entradas fallaron durante la descarga."

        return DownloadResult(
            request=request,
            status=status,
            output_path=request.output_directory,
            title=info.get("title"),
            error_message=error_message,
            entry_count=total,
            entry_failures=failures,
        )

    def iter_collection_entry_results(
        self, request: DownloadRequest, info: dict[str, Any]
    ) -> list[DownloadResult]:
        """Devuelve un `DownloadResult` por cada entrada individual de una
        playlist/canal ya descargada, para que el historial registre cada
        video por separado en vez de una única fila agregada (corrige B4).
        """
        results: list[DownloadResult] = []
        for entry in info.get("entries") or []:
            if entry is None:
                results.append(
                    DownloadResult(
                        request=request,
                        status=DownloadStatus.FAILED,
                        output_path=None,
                        title=None,
                        error_message="La entrada no pudo extraerse (video privado, eliminado o región bloqueada).",
                    )
                )
                continue

            requested = entry.get("requested_downloads") or []
            final_path = Path(requested[0]["filepath"]) if requested else None
            results.append(
                DownloadResult(
                    request=request,
                    status=DownloadStatus.COMPLETED if requested else DownloadStatus.FAILED,
                    output_path=final_path,
                    title=entry.get("title"),
                    error_message=None if requested else "Sin descargas asociadas a esta entrada.",
                )
            )
        return results

    def download_collection(
        self, request: DownloadRequest, progress_callback: ProgressCallback | None = None
    ) -> tuple[DownloadResult, list[DownloadResult]]:
        """Descarga una playlist/canal y devuelve tanto el resumen agregado
        como un `DownloadResult` por cada entrada individual (para que el
        historial registre cada video por separado — corrige B4).

        Hace una única llamada a `extract_info(download=True)`; no repite
        trabajo respecto a `download()`.
        """
        if request.kind not in (DownloadKind.PLAYLIST, DownloadKind.CHANNEL):
            raise ValueError("download_collection() solo aplica a PLAYLIST/CHANNEL")

        opts = self._build_ydl_opts(request, progress_callback)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            logger.error("Fallo al descargar la colección %s: %s", request.url, exc)
            failed = DownloadResult(
                request=request, status=DownloadStatus.FAILED, output_path=None, title=None, error_message=str(exc)
            )
            return failed, []

        if info is None:
            failed = DownloadResult(
                request=request,
                status=DownloadStatus.FAILED,
                output_path=None,
                title=None,
                error_message="yt-dlp no devolvió metadatos para esta URL.",
            )
            return failed, []

        summary = self._summarize_collection_result(request, info)
        entries = self.iter_collection_entry_results(request, info) if info.get("entries") else []
        return summary, entries

    def extract_metadata_only(self, url: str) -> dict[str, Any]:
        """Extrae metadatos sin descargar (usado por `search` y `doctor`)."""
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            raise DownloadError(f"No se pudieron extraer metadatos de: {url}")
        return info
