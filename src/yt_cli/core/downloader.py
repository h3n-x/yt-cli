"""Wrapper sobre la API Python de yt-dlp (no la CLI de yt-dlp).

Se usa deliberadamente `yt_dlp.YoutubeDL` como librería en vez de invocar el
binario `yt-dlp` como subproceso: esto evita construir comandos por
concatenación de strings (fuente típica de command injection) y permite
recibir progreso estructurado vía hooks en vez de parsear stdout.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import yt_dlp
import yt_dlp.utils

from yt_cli.core.dependencies import MUTAGEN_THUMBNAIL_FORMATS, has_mutagen
from yt_cli.core.errors import clean_message, explain
from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import AudioQuality, DownloadStatus, MediaType, OverwritePolicy
from yt_cli.models.results import (
    DownloadResult,
    EntryResult,
    ProgressCallback,
    ProgressEvent,
)

# Reexportados por compatibilidad: antes de 0.4.0 vivían en este módulo.
__all__ = [
    "DownloadError",
    "DownloadResult",
    "EntryResult",
    "ProgressCallback",
    "ProgressEvent",
    "YtDlpDownloader",
]

logger = logging.getLogger("yt_cli.downloader")

# Backoff exponencial acotado para reintentos de red. yt-dlp, sin configurar
# `retry_sleep_functions`, reintenta inmediatamente sin pausa alguna entre
# intentos. Se acota el techo para no bloquear indefinidamente una descarga
# ante un fallo persistente.
_RETRY_SLEEP_FUNCTIONS: dict[str, Callable[[int], float]] = {
    "http": lambda n: min(4 * (2**n), 60),
    "fragment": lambda n: min(2 * (2**n), 30),
    "file_access": lambda n: min(1 * (2**n), 10),
}

# Contenedores en los que yt-dlp sabe incrustar una miniatura
# (yt_dlp/postprocessor/embedthumbnail.py). En el resto (webm, wav, aac)
# EmbedThumbnail lanza un error que aborta la descarga ya completada.
_THUMBNAIL_CONTAINERS = frozenset(
    {"mp3", "mkv", "mka", "ogg", "opus", "flac", "m4a", "mp4", "m4v", "mov"}
)

# Claves de `[ytdlp]` en config.toml que no se pueden sobrescribir porque
# yt-cli depende de ellas para funcionar (progreso, logging, rutas, formato).
PROTECTED_YTDLP_OPTIONS = frozenset(
    {
        "outtmpl",
        "paths",
        "format",
        "postprocessors",
        "progress_hooks",
        "postprocessor_hooks",
        "logger",
        "quiet",
        "noprogress",
        "color",
        "noplaylist",
        "ignoreerrors",
        "playlist_items",
        "download_archive",
        "overwrites",
    }
)

_TEMPLATE_FIELDS = {
    "{title}": "%(title)s",
    "{uploader}": "%(uploader)s",
    "{date}": "%(upload_date)s",
    "{id}": "%(id)s",
    "{playlist}": "%(playlist_title)s",
    "{resolution}": "%(height)sp",
    "{ext}": "%(ext)s",
}


class DownloadError(RuntimeError):
    """Fallo irrecuperable al consultar o descargar con yt-dlp."""


class _YtDlpLogBridge:
    """Logger que se entrega a yt-dlp en vez de dejarle escribir en la terminal.

    - Ningún mensaje de yt-dlp se imprime en modo normal: la CLI informa de los
      errores una sola vez, ya traducidos (ver `core/errors.py`). Con `--debug`
      todo queda visible vía el logger `yt_dlp`.
    - Los errores se acumulan en orden, para poder asociarlos a las entradas
      fallidas de una colección.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        # Secuencia ordenada de entradas sin resultado: ("error", mensaje) o
        # ("skipped", id). Permite asignar cada `None` de `info["entries"]` a
        # su causa real (un fallo o un video ya registrado en el archivo).
        self.entry_events: list[tuple[str, str]] = []
        self._log = logging.getLogger("yt_dlp")

    def debug(self, msg: str) -> None:
        if "has already been recorded in the archive" in msg:
            self.entry_events.append(("skipped", clean_message(msg)))
        self._log.debug(msg)

    def info(self, msg: str) -> None:
        self._log.debug(msg)

    def warning(self, msg: str) -> None:
        self.warnings.append(clean_message(msg))
        self._log.info("WARNING: %s", msg)

    def error(self, msg: str) -> None:
        cleaned = clean_message(msg)
        self.errors.append(cleaned)
        self.entry_events.append(("error", cleaned))
        self._log.info("%s", msg)


def build_output_template(request: DownloadRequest) -> str:
    """Traduce la plantilla propia de yt-cli ({title}, {uploader}, ...) al
    formato de outtmpl que espera yt-dlp (%(title)s, %(uploader)s, ...).
    """
    # Un '%' literal escrito por el usuario debe escaparse para yt-dlp.
    template = request.filename_template.replace("%", "%%")
    for placeholder, yt_dlp_field in _TEMPLATE_FIELDS.items():
        template = template.replace(placeholder, yt_dlp_field)
    output_dir = str(request.output_directory).replace("%", "%%")
    return f"{output_dir}/{template}"


def thumbnail_embedding_supported(request: DownloadRequest) -> bool:
    """Indica si el contenedor final admite carátula incrustada con las
    dependencias instaladas (opus/ogg/flac requieren `mutagen`).
    """
    ext = request.target_extension
    if ext not in _THUMBNAIL_CONTAINERS:
        return False
    return not (ext in MUTAGEN_THUMBNAIL_FORMATS and not has_mutagen())


def build_postprocessors(request: DownloadRequest) -> list[dict[str, Any]]:
    postprocessors: list[dict[str, Any]] = []

    if request.sponsorblock_remove:
        postprocessors.append(
            {
                "key": "SponsorBlock",
                "categories": list(request.sponsorblock_remove),
                "when": "after_filter",
            }
        )

    if request.media is MediaType.AUDIO:
        preferred_quality = (
            "0" if request.audio_quality is AudioQuality.BEST else str(request.audio_quality.kbps)
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
            {"key": "FFmpegVideoConvertor", "preferedformat": request.video_format.value}
        )

    if request.sponsorblock_remove:
        # ModifyChapters debe ir antes de FFmpegMetadata (igual que en yt-dlp).
        postprocessors.append(
            {
                "key": "ModifyChapters",
                "remove_sponsor_segments": list(request.sponsorblock_remove),
            }
        )

    if request.embed_metadata:
        postprocessors.append({"key": "FFmpegMetadata", "add_chapters": request.embed_chapters})
    if request.download_subtitles:
        postprocessors.append({"key": "FFmpegEmbedSubtitle"})
    if request.embed_thumbnail and thumbnail_embedding_supported(request):
        postprocessors.append({"key": "EmbedThumbnail"})

    return postprocessors


def map_yt_dlp_progress(data: Mapping[str, Any]) -> ProgressEvent:
    status_map = {
        "downloading": DownloadStatus.DOWNLOADING,
        "finished": DownloadStatus.CONVERTING,
        "error": DownloadStatus.FAILED,
    }
    total = data.get("total_bytes") or data.get("total_bytes_estimate")
    downloaded = data.get("downloaded_bytes")
    percent = (downloaded / total * 100) if total and downloaded is not None else None

    info = data.get("info_dict") or {}
    return ProgressEvent(
        status=status_map.get(data.get("status", ""), DownloadStatus.DOWNLOADING),
        filename=data.get("filename"),
        downloaded_bytes=downloaded,
        total_bytes=total,
        speed_bps=data.get("speed"),
        eta_seconds=data.get("eta"),
        percent=percent,
        playlist_index=info.get("playlist_index"),
        playlist_count=info.get("n_entries") or info.get("playlist_count"),
    )


# Alias con el nombre anterior a 0.4.0 (usado por los tests existentes).
_map_yt_dlp_progress = map_yt_dlp_progress


def _final_path(info: Mapping[str, Any]) -> Path | None:
    requested = info.get("requested_downloads") or []
    if requested and requested[0].get("filepath"):
        return Path(requested[0]["filepath"])
    return None


class YtDlpDownloader:
    """Ejecuta descargas usando la API de yt-dlp.

    Es seguro usar una misma instancia desde varios hilos (`batch`): cada
    descarga crea su propio `YoutubeDL`. `cancel()` pide a todas las descargas
    en curso que se detengan en el siguiente evento de progreso.
    """

    def __init__(
        self,
        *,
        max_concurrent_fragments: int = 4,
        retries: int = 10,
        proxy: str | None = None,
        rate_limit_kbps: int | None = None,
        cookies_from_browser: str | None = None,
        extra_options: Mapping[str, Any] | None = None,
    ) -> None:
        self._max_concurrent_fragments = max_concurrent_fragments
        self._retries = retries
        self._proxy = proxy
        self._rate_limit_kbps = rate_limit_kbps
        self._cookies_from_browser = cookies_from_browser
        self._extra_options = dict(extra_options or {})
        self._cancelled = threading.Event()

    # ------------------------------------------------------------------ opciones

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def _base_opts(self, log_bridge: _YtDlpLogBridge) -> dict[str, Any]:
        """Opciones comunes a descargas y consultas de metadatos (red, cookies,
        logging), para que `search` y la resolución de RENAME respeten el proxy
        y las cookies igual que una descarga.
        """
        opts: dict[str, Any] = {
            "retries": self._retries,
            "fragment_retries": self._retries,
            "retry_sleep_functions": _RETRY_SLEEP_FUNCTIONS,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            # Sin colores: el texto se reenvía a nuestro logger y se mostraría
            # como basura ('[1m[0;31mERROR:') al pasar por Rich.
            "color": {"stdout": "never", "stderr": "never"},
            "logger": log_bridge,
        }
        if self._proxy:
            opts["proxy"] = self._proxy
        if self._cookies_from_browser:
            # "firefox" o "chrome:Perfil 1" → la tupla (navegador, perfil,
            # keyring, contenedor) que espera la API de yt-dlp.
            browser, _, profile = self._cookies_from_browser.partition(":")
            opts["cookiesfrombrowser"] = (browser.lower(), profile or None, None, None)

        for key, value in self._extra_options.items():
            if key in PROTECTED_YTDLP_OPTIONS:
                logger.warning("Opción [ytdlp].%s ignorada: yt-cli la gestiona internamente.", key)
                continue
            opts[key] = value
        return opts

    def _build_ydl_opts(
        self,
        request: DownloadRequest,
        progress_callback: ProgressCallback | None,
        log_bridge: _YtDlpLogBridge | None = None,
    ) -> dict[str, Any]:
        opts = self._base_opts(log_bridge or _YtDlpLogBridge())
        opts.update(
            {
                "outtmpl": build_output_template(request),
                "format": (
                    "bestaudio/best"
                    if request.media is MediaType.AUDIO
                    else request.video_quality.as_yt_dlp_format()
                ),
                "postprocessors": build_postprocessors(request),
                "noplaylist": not request.scope.is_collection,
                # En una colección, un video no disponible no debe abortar el
                # resto: yt-dlp registra el error y continúa con la siguiente.
                "ignoreerrors": request.scope.is_collection,
                "concurrent_fragment_downloads": self._max_concurrent_fragments,
                "continuedl": True,  # reanudación automática
                "nopart": False,
                # overwrites=False hace que yt-dlp omita la redescarga si el
                # archivo ya existe en la ruta final (política SKIP).
                "overwrites": request.overwrite_policy is OverwritePolicy.OVERWRITE,
                "writethumbnail": request.embed_thumbnail
                and thumbnail_embedding_supported(request),
                "writesubtitles": request.download_subtitles,
                "subtitleslangs": request.subtitle_languages or ["en"],
            }
        )

        if request.playlist_items:
            opts["playlist_items"] = request.playlist_items
        if request.download_archive is not None:
            request.download_archive.parent.mkdir(parents=True, exist_ok=True)
            opts["download_archive"] = str(request.download_archive)
        if self._rate_limit_kbps:
            # yt-dlp espera bytes/segundo; la configuración del usuario está en kbps.
            opts["ratelimit"] = self._rate_limit_kbps * 1024

        def _hook(data: dict[str, Any]) -> None:
            if self._cancelled.is_set():
                raise yt_dlp.utils.DownloadCancelled("Cancelado por el usuario.")
            if progress_callback is not None:
                progress_callback(map_yt_dlp_progress(data))

        opts["progress_hooks"] = [_hook]
        return opts

    # ------------------------------------------------------------- metadatos

    def extract_metadata_only(self, url: str, *, flat: bool = False) -> dict[str, Any]:
        """Extrae metadatos sin descargar (usado por `search` y RENAME).

        Lanza `DownloadError` (propio) ante cualquier fallo de yt-dlp, para que
        quien llama no necesite importar yt-dlp.
        """
        bridge = _YtDlpLogBridge()
        opts = self._base_opts(bridge)
        opts["skip_download"] = True
        if flat:
            opts["extract_flat"] = "in_playlist"
        try:
            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise DownloadError(str(explain(str(exc)))) from exc
        if info is None:
            raise DownloadError(f"No se pudieron extraer metadatos de: {url}")
        return cast(dict[str, Any], ydl.sanitize_info(info))

    def _resolve_rename_target(self, request: DownloadRequest) -> str | None:
        """Para overwrite_policy=RENAME: calcula la ruta final exactamente como
        la calcularía yt-dlp (`prepare_filename`, misma sanitización) y, si ya
        existe, le añade un sufijo ' (n)' hasta encontrar una ruta libre.

        Devuelve la ruta final elegida, o None si no se pudo determinar (en ese
        caso se descarga sin renombrar en vez de fallar).
        """
        try:
            info = self.extract_metadata_only(request.url)
        except DownloadError:
            return None

        opts = {"outtmpl": build_output_template(request), "quiet": True}
        with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
            prepared = Path(ydl.prepare_filename(info))
        target = prepared.with_suffix(f".{request.target_extension}")

        if not target.exists():
            return str(target)

        counter = 1
        while True:
            candidate = target.with_name(f"{target.stem} ({counter}){target.suffix}")
            if not candidate.exists():
                return str(candidate)
            counter += 1

    # ------------------------------------------------------------- descargas

    def download(
        self, request: DownloadRequest, progress_callback: ProgressCallback | None = None
    ) -> DownloadResult:
        """Descarga un video o una colección. Nunca lanza por un fallo de la
        descarga en sí: el resultado lleva el estado y el mensaje de error.
        """
        if request.scope.is_collection:
            return self.download_collection(request, progress_callback)

        bridge = _YtDlpLogBridge()
        opts = self._build_ydl_opts(request, progress_callback, bridge)

        if request.overwrite_policy is OverwritePolicy.RENAME:
            target = self._resolve_rename_target(request)
            if target is not None:
                stem = str(Path(target).with_suffix("")).replace("%", "%%")
                opts["outtmpl"] = f"{stem}.%(ext)s"
                opts["overwrites"] = True  # ya elegimos una ruta libre

        outcome = self._run(request, opts, bridge)
        if isinstance(outcome, DownloadResult):
            return outcome

        return DownloadResult(
            request=request,
            status=DownloadStatus.COMPLETED,
            output_path=_final_path(outcome),
            title=outcome.get("title"),
        )

    def download_collection(
        self, request: DownloadRequest, progress_callback: ProgressCallback | None = None
    ) -> DownloadResult:
        """Descarga una playlist/canal con una única llamada a yt-dlp y
        devuelve el resumen con un `EntryResult` por cada entrada.
        """
        if not request.scope.is_collection:
            raise ValueError("download_collection() solo aplica a playlists/canales")

        bridge = _YtDlpLogBridge()
        opts = self._build_ydl_opts(request, progress_callback, bridge)
        outcome = self._run(request, opts, bridge)
        if isinstance(outcome, DownloadResult):
            return outcome
        return self._summarize_collection_result(
            request, outcome, errors=bridge.errors, entry_events=bridge.entry_events
        )

    def _run(
        self, request: DownloadRequest, opts: dict[str, Any], bridge: _YtDlpLogBridge
    ) -> dict[str, Any] | DownloadResult:
        """Ejecuta yt-dlp. Devuelve el `info` de yt-dlp si todo fue bien, o un
        `DownloadResult` FAILED/CANCELLED que describe el fallo.
        """

        def failed(status: DownloadStatus, message: str) -> DownloadResult:
            return DownloadResult(
                request=request, status=status, output_path=None, title=None, error_message=message
            )

        if self._cancelled.is_set():
            return failed(DownloadStatus.CANCELLED, "Cancelado por el usuario.")

        try:
            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                info = ydl.extract_info(request.url, download=True)
        except yt_dlp.utils.DownloadCancelled:
            return failed(DownloadStatus.CANCELLED, "Cancelado por el usuario.")
        except yt_dlp.utils.DownloadError as exc:
            message = bridge.errors[-1] if bridge.errors else str(exc)
            return failed(DownloadStatus.FAILED, str(explain(message)))
        except OSError as exc:  # disco lleno, permisos, ruta inválida
            return failed(DownloadStatus.FAILED, f"Error de sistema de archivos: {exc}")

        if info is None:
            message = bridge.errors[-1] if bridge.errors else "yt-dlp no devolvió metadatos."
            return failed(DownloadStatus.FAILED, str(explain(message)))
        return cast(dict[str, Any], info)

    def _summarize_collection_result(
        self,
        request: DownloadRequest,
        info: Mapping[str, Any],
        *,
        errors: list[str] | None = None,
        entry_events: list[tuple[str, str]] | None = None,
    ) -> DownloadResult:
        """Inspecciona `info['entries']` y reporta con precisión cuántas
        entradas se completaron vs. fallaron.
        """
        entries = list(info.get("entries") or [])

        if not entries:
            # La URL resolvió a un único video (p. ej. un canal con un solo
            # video público): se trata como una colección de 1.
            path = _final_path(info)
            status = DownloadStatus.COMPLETED if path else DownloadStatus.FAILED
            entry = EntryResult(
                status=status,
                title=info.get("title"),
                url=info.get("webpage_url") or request.url,
                output_path=path,
                error_message=None if path else _first_error(errors),
            )
            return DownloadResult(
                request=request,
                status=status,
                output_path=path,
                title=info.get("title"),
                error_message=entry.error_message,
                entry_count=1,
                entry_failures=0 if path else 1,
                entries=[entry],
            )

        entry_results = self.iter_collection_entry_results(
            request,
            info,
            entry_events=entry_events
            if entry_events is not None
            else [("error", e) for e in errors or []],
        )
        failures = sum(1 for e in entry_results if e.status is DownloadStatus.FAILED)
        total = len(entry_results)
        if failures == 0:
            status = DownloadStatus.COMPLETED
        elif failures == total:
            status = DownloadStatus.FAILED
        else:
            status = DownloadStatus.PARTIAL

        return DownloadResult(
            request=request,
            status=status,
            output_path=request.output_directory,
            title=info.get("title"),
            error_message=f"{failures}/{total} entradas fallaron." if failures else None,
            entry_count=total,
            entry_failures=failures,
            entries=entry_results,
        )

    def iter_collection_entry_results(
        self,
        request: DownloadRequest,
        info: Mapping[str, Any],
        *,
        entry_events: list[tuple[str, str]] | None = None,
    ) -> list[EntryResult]:
        """Un `EntryResult` por entrada. Las entradas sin resultado llegan
        como `None`; se les asigna, en orden, el evento que yt-dlp registró
        para ellas: un error, o un salto por estar ya en el archivo de descargas.
        """
        pending = list(entry_events or [])
        results: list[EntryResult] = []
        for entry in info.get("entries") or []:
            if entry is None:
                results.append(_entry_without_result(pending.pop(0) if pending else None))
                continue

            path = _final_path(entry)
            results.append(
                EntryResult(
                    status=DownloadStatus.COMPLETED if path else DownloadStatus.FAILED,
                    title=entry.get("title"),
                    url=entry.get("webpage_url") or _watch_url(entry.get("id")),
                    output_path=path,
                    error_message=None if path else "Sin archivo descargado para esta entrada.",
                )
            )
        return results


def _entry_without_result(event: tuple[str, str] | None) -> EntryResult:
    if event is not None and event[0] == "skipped":
        return EntryResult(
            status=DownloadStatus.SKIPPED,
            title=None,
            url=None,
            output_path=None,
            error_message="Ya descargado (registrado en el archivo de descargas).",
        )
    explained = explain(event[1]) if event is not None else None
    return EntryResult(
        status=DownloadStatus.FAILED,
        title=None,
        url=_watch_url(explained.video_id) if explained else None,
        output_path=None,
        error_message=str(explained)
        if explained
        else "La entrada no pudo extraerse (privada, eliminada o bloqueada).",
    )


def _first_error(errors: list[str] | None) -> str | None:
    return str(explain(errors[0])) if errors else None


def _watch_url(video_id: str | None) -> str | None:
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else None
