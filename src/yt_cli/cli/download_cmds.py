"""Comandos que descargan o consultan YouTube."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from pydantic import ValidationError
from rich.markup import escape
from rich.table import Table

from yt_cli.cli._app import (
    EXIT_FAILURE,
    EXIT_INTERRUPTED,
    EXIT_PARTIAL,
    app,
    console,
    error_console,
    fail,
    info,
    state,
    success,
    warn,
)
from yt_cli.config.manager import ConfigError, load_config
from yt_cli.config.models import AppConfig, DownloadDefaults
from yt_cli.core.dependencies import (
    MUTAGEN_THUMBNAIL_FORMATS,
    FFmpegNotFoundError,
    find_js_runtime,
    has_mutagen,
    require_ffmpeg,
)
from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import (
    AudioFormat,
    AudioQuality,
    DownloadStatus,
    MediaType,
    Scope,
    VideoFormat,
    VideoQuality,
)
from yt_cli.models.results import DownloadResult, ProgressCallback, ProgressEvent
from yt_cli.services.download_service import build_downloader, build_request, record_history

if TYPE_CHECKING:
    from yt_cli.services.queue import QueueSummary
from yt_cli.utils.theme import STATUS_ICON, TABLE_BOX, ZEBRA_ROW_STYLES
from yt_cli.utils.validators import InvalidURLError, validate_urls

# ---------------------------------------------------------------- opciones comunes

OutputOpt = Annotated[
    Path | None,
    typer.Option(
        "--output", "-o", help="Directorio de salida (por defecto, general.download_directory)."
    ),
]
TemplateOpt = Annotated[
    str | None,
    typer.Option(
        "--template",
        help="Plantilla de nombre: {title} {uploader} {date} {id} {playlist} {resolution} {ext}.",
    ),
]
ItemsOpt = Annotated[
    str | None,
    typer.Option(
        "--items",
        "-I",
        help="Solo estas entradas de una playlist/canal, p. ej. '1:10' o '1,3,5-7'.",
    ),
]
ArchiveOpt = Annotated[
    bool | None,
    typer.Option(
        "--archive/--no-archive",
        help="Saltar videos ya descargados antes (archivo de descargas de yt-dlp).",
        show_default=False,
    ),
]
AudioOnlyOpt = Annotated[
    bool, typer.Option("--audio", "-a", help="Descargar solo el audio de cada video.")
]
CollectionFormatOpt = Annotated[
    str | None,
    typer.Option(
        "--format",
        "-f",
        help="Formato de salida: mp4/mkv/webm/mov, o con --audio mp3/opus/m4a/flac/ogg/wav/aac.",
    ),
]
CollectionQualityOpt = Annotated[
    str | None,
    typer.Option(
        "--quality",
        "-q",
        help="Calidad: 144p…2160p/best, o con --audio 64k…320k/best.",
    ),
]


def _load_config() -> AppConfig:
    try:
        return load_config()
    except ConfigError as exc:
        fail(str(exc))


def _effective_downloads(config: AppConfig) -> DownloadDefaults:
    """Valores de descarga del perfil pedido con `--profile`, o los globales."""
    try:
        return config.resolve_downloads(state.profile)
    except KeyError as exc:
        fail(str(exc.args[0]))


def _parse_choice[E: StrEnum](enum_cls: type[E], value: str | None, option: str) -> E | None:
    if value is None:
        return None
    try:
        return enum_cls(value.lower())
    except ValueError:
        valid = ", ".join(member.value for member in enum_cls)
        fail(f"Valor inválido para {option}: '{value}'. Opciones: {valid}.")


def _validation_message(exc: ValidationError | ValueError) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(str(err["msg"]).removeprefix("Value error, ") for err in exc.errors())
    return str(exc)


# ------------------------------------------------------------------ ejecución


def _preflight(requests: list[DownloadRequest]) -> None:
    """Comprueba antes de descargar lo que haría fallar la descarga a mitad
    de camino (ffmpeg) y avisa de lo que la degradaría (runtime JS, mutagen).
    """
    try:
        require_ffmpeg()
    except FFmpegNotFoundError as exc:
        fail(str(exc))

    if find_js_runtime() is None:
        warn(
            "No se encontró un runtime de JavaScript (deno, node, bun o qjs). YouTube exige "
            "resolver retos JS y muchas descargas fallarán. Instálalo con: sudo pacman -S deno"
        )

    needs_mutagen = any(
        r.embed_thumbnail and r.target_extension in MUTAGEN_THUMBNAIL_FORMATS for r in requests
    )
    if needs_mutagen and not has_mutagen():
        warn(
            "No se incrustará la carátula: opus/ogg/flac requieren el módulo 'mutagen' "
            "(sudo pacman -S python-mutagen)."
        )


def _run_with_progress(config: AppConfig, request: DownloadRequest) -> DownloadResult:
    from yt_cli.utils.progress_ui import RichDownloadProgress

    _preflight([request])
    downloader = build_downloader(config)

    with RichDownloadProgress(console) as progress_ui:
        task_id = progress_ui.add_task(request.url)

        def on_progress(event: ProgressEvent) -> None:
            progress_ui.update(task_id, event)

        try:
            result = downloader.download(request, progress_callback=on_progress)
        except KeyboardInterrupt:
            # Click convertiría Ctrl+C en "Aborted!" con código 1; se informa
            # como cancelación (código 130) y se conserva el historial parcial.
            downloader.cancel()
            result = DownloadResult(
                request=request,
                status=DownloadStatus.CANCELLED,
                output_path=None,
                title=None,
                error_message="Cancelado por el usuario.",
            )
        progress_ui.finish(task_id, result)

    record_history(config, [result])
    return result


def _report(result: DownloadResult) -> None:
    """Informa del resultado una sola vez y termina con el código adecuado."""
    if result.status is DownloadStatus.CANCELLED:
        error_console.print("[warning]Descarga cancelada.[/warning]")
        raise typer.Exit(code=EXIT_INTERRUPTED)

    if not result.request.scope.is_collection:
        if result.status is not DownloadStatus.COMPLETED:
            fail(result.error_message or "La descarga falló por un motivo desconocido.")
        if result.output_path:
            success(f"Guardado en {result.output_path}")
        return

    entries = result.entries
    if not entries:
        if result.status is DownloadStatus.COMPLETED:
            success("Colección descargada.")
            return
        # La colección falló antes de listar entradas (red, URL, extractor).
        fail(result.error_message or "No se pudo descargar la colección.")

    completed = sum(1 for e in entries if e.status is DownloadStatus.COMPLETED)
    skipped = sum(1 for e in entries if e.status is DownloadStatus.SKIPPED)
    failed = [e for e in entries if e.status is DownloadStatus.FAILED]

    console.rule(style="border")
    parts = [f"[success]{completed} descargadas[/success]"]
    if skipped:
        parts.append(f"[muted]{skipped} ya descargadas antes[/muted]")
    if failed:
        parts.append(f"[error]{len(failed)} fallidas[/error]")
    console.print(" · ".join(parts))

    for entry in failed:
        name = entry.title or entry.url or "entrada desconocida"
        console.print(
            f"  [error]{STATUS_ICON[DownloadStatus.FAILED]}[/error] {escape(name)}: "
            f"[muted]{escape(entry.error_message or 'error desconocido')}[/muted]"
        )

    if result.status is DownloadStatus.FAILED:
        raise typer.Exit(code=EXIT_FAILURE)
    if result.status is DownloadStatus.PARTIAL:
        console.print("[muted]Detalle completo: yt-cli history[/muted]")
        raise typer.Exit(code=EXIT_PARTIAL)


def _download_one(
    url: str,
    *,
    media: MediaType,
    scope: Scope | None = None,
    output: Path | None,
    template: str | None,
    video_format: VideoFormat | None = None,
    audio_format: AudioFormat | None = None,
    video_quality: VideoQuality | None = None,
    audio_quality: AudioQuality | None = None,
    items: str | None = None,
    archive: bool | None = None,
) -> None:
    config = _load_config()
    defaults = _effective_downloads(config)
    try:
        request = build_request(
            url,
            media=media,
            scope=scope,
            config=config,
            defaults=defaults,
            output=output,
            template=template,
            video_format=video_format,
            audio_format=audio_format,
            video_quality=video_quality,
            audio_quality=audio_quality,
            playlist_items=items,
            use_archive=archive,
        )
    except (InvalidURLError, ValidationError, ValueError) as exc:
        fail(_validation_message(exc))

    if request.scope.is_collection:
        label = "Canal" if request.scope is Scope.CHANNEL else "Playlist"
        mode = "audio" if request.media is MediaType.AUDIO else "video"
        console.rule(f"[header]{label} ({mode})[/header]", style="border")

    _report(_run_with_progress(config, request))


# ------------------------------------------------------------------ comandos


@app.command()
def download(
    url: Annotated[str, typer.Argument(help="URL de un video, playlist o canal de YouTube.")],
    format: Annotated[
        VideoFormat | None, typer.Option("--format", "-f", help="Contenedor de salida.")
    ] = None,
    quality: Annotated[
        VideoQuality | None, typer.Option("--quality", "-q", help="Calidad de video objetivo.")
    ] = None,
    output: OutputOpt = None,
    template: TemplateOpt = None,
    items: ItemsOpt = None,
    archive: ArchiveOpt = None,
) -> None:
    """Descarga un video. Si la URL es una playlist o canal, los descarga completos."""
    _download_one(
        url,
        media=MediaType.VIDEO,
        output=output,
        template=template,
        video_format=format,
        video_quality=quality,
        items=items,
        archive=archive,
    )


@app.command()
def audio(
    url: Annotated[str, typer.Argument(help="URL de un video, playlist o canal de YouTube.")],
    format: Annotated[
        AudioFormat | None, typer.Option("--format", "-f", help="Formato de audio de salida.")
    ] = None,
    quality: Annotated[
        AudioQuality | None, typer.Option("--quality", "-q", help="Bitrate objetivo.")
    ] = None,
    output: OutputOpt = None,
    template: TemplateOpt = None,
    items: ItemsOpt = None,
    archive: ArchiveOpt = None,
) -> None:
    """Descarga solo el audio (también de playlists y álbumes de YouTube Music)."""
    _download_one(
        url,
        media=MediaType.AUDIO,
        output=output,
        template=template,
        audio_format=format,
        audio_quality=quality,
        items=items,
        archive=archive,
    )


def _collection_command(
    url: str,
    scope: Scope,
    *,
    audio_only: bool,
    format: str | None,
    quality: str | None,
    output: Path | None,
    template: str | None,
    items: str | None,
    archive: bool | None,
) -> None:
    if audio_only:
        _download_one(
            url,
            media=MediaType.AUDIO,
            scope=scope,
            output=output,
            template=template,
            audio_format=_parse_choice(AudioFormat, format, "--format"),
            audio_quality=_parse_choice(AudioQuality, quality, "--quality"),
            items=items,
            archive=archive,
        )
    else:
        _download_one(
            url,
            media=MediaType.VIDEO,
            scope=scope,
            output=output,
            template=template,
            video_format=_parse_choice(VideoFormat, format, "--format"),
            video_quality=_parse_choice(VideoQuality, quality, "--quality"),
            items=items,
            archive=archive,
        )


@app.command()
def playlist(
    url: Annotated[str, typer.Argument(help="URL de la playlist (YouTube o YouTube Music).")],
    audio_only: AudioOnlyOpt = False,
    format: CollectionFormatOpt = None,
    quality: CollectionQualityOpt = None,
    output: OutputOpt = None,
    template: TemplateOpt = None,
    items: ItemsOpt = None,
    archive: ArchiveOpt = None,
) -> None:
    """Descarga una playlist completa (en video, o en audio con --audio)."""
    _collection_command(
        url,
        Scope.PLAYLIST,
        audio_only=audio_only,
        format=format,
        quality=quality,
        output=output,
        template=template,
        items=items,
        archive=archive,
    )


@app.command()
def channel(
    url: Annotated[str, typer.Argument(help="URL del canal de YouTube.")],
    audio_only: AudioOnlyOpt = False,
    format: CollectionFormatOpt = None,
    quality: CollectionQualityOpt = None,
    output: OutputOpt = None,
    template: TemplateOpt = None,
    items: ItemsOpt = None,
    archive: ArchiveOpt = None,
) -> None:
    """Descarga todos los videos públicos de un canal (o su audio con --audio)."""
    _collection_command(
        url,
        Scope.CHANNEL,
        audio_only=audio_only,
        format=format,
        quality=quality,
        output=output,
        template=template,
        items=items,
        archive=archive,
    )


@app.command()
def batch(
    file: Annotated[
        Path,
        typer.Argument(
            help="Archivo de texto con una URL por línea ('#' para comentarios).",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    output: OutputOpt = None,
    audio_only: Annotated[
        bool, typer.Option("--audio", "-a", help="Descargar solo audio para todas las URLs.")
    ] = False,
    archive: ArchiveOpt = None,
) -> None:
    """Descarga en paralelo todas las URLs listadas en un archivo de texto."""
    import asyncio

    from yt_cli.services.queue import DownloadQueue
    from yt_cli.utils.progress_ui import RichDownloadProgress

    urls = _read_batch_urls(file)
    config = _load_config()
    defaults = _effective_downloads(config)
    media = MediaType.AUDIO if audio_only else MediaType.VIDEO
    try:
        requests = [
            build_request(
                u, media=media, config=config, defaults=defaults, output=output, use_archive=archive
            )
            for u in urls
        ]
    except (ValidationError, ValueError) as exc:
        fail(_validation_message(exc))

    _preflight(requests)
    downloader = build_downloader(config)
    dqueue = DownloadQueue(downloader, max_concurrent=config.network.max_concurrent_downloads)
    results: list[DownloadResult | None] = [None] * len(requests)

    with RichDownloadProgress(console) as progress_ui:
        # Indexado por posición, no por URL: una URL repetida en el archivo
        # tiene su propia barra.
        task_ids = [progress_ui.add_task(req.url) for req in requests]

        def progress_factory(index: int, _req: DownloadRequest) -> ProgressCallback:
            def _cb(event: ProgressEvent) -> None:
                progress_ui.update(task_ids[index], event)

            return _cb

        def on_result(index: int, result: DownloadResult) -> None:
            results[index] = result
            progress_ui.finish(task_ids[index], result)

        try:
            summary = asyncio.run(
                dqueue.run_all(
                    requests, progress_callback_factory=progress_factory, on_result=on_result
                )
            )
        except KeyboardInterrupt:
            summary = None

    finished = [r for r in results if r is not None]
    record_history(config, finished)

    if summary is None:
        error_console.print("[warning]Descargas canceladas por el usuario.[/warning]")
        raise typer.Exit(code=EXIT_INTERRUPTED)

    _print_batch_summary(summary, finished)
    if summary.failed:
        raise typer.Exit(code=EXIT_FAILURE)


def _read_batch_urls(file: Path) -> list[str]:
    """URLs válidas del archivo de `batch` (ignora líneas vacías y '#')."""
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        fail(f"No se pudo leer '{file}': {exc}")

    raw_lines = [
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    ]
    try:
        urls = validate_urls(raw_lines)
    except InvalidURLError as exc:
        fail(str(exc))
    if not urls:
        fail(f"'{file}' no contiene ninguna URL válida.")
    return urls


def _print_batch_summary(summary: QueueSummary, results: list[DownloadResult]) -> None:
    console.rule(style="border")
    summary_style = "success" if summary.failed == 0 else "warning"
    console.print(
        f"[{summary_style}]Resumen:[/{summary_style}] "
        f"[success]{summary.completed}[/success]/{summary.total} completadas"
        + (f", [error]{summary.failed}[/error] fallidas." if summary.failed else ".")
    )
    icon = STATUS_ICON[DownloadStatus.FAILED]
    for result in results:
        if result.status is DownloadStatus.FAILED:
            console.print(
                f"  [error]{icon}[/error] {escape(result.request.url)}: "
                f"[muted]{escape(result.error_message or 'error desconocido')}[/muted]"
            )


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Consulta de búsqueda.")],
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=50)] = 10,
    json_output: Annotated[
        bool, typer.Option("--json", help="Salida en formato JSON (para scripting).")
    ] = False,
) -> None:
    """Busca videos en YouTube y muestra resultados en una tabla."""
    from contextlib import nullcontext

    from yt_cli.core.downloader import DownloadError
    from yt_cli.services.cache import MetadataCache

    config = _load_config()
    search_url = f"ytsearch{limit}:{query}"
    ttl = config.general.cache_ttl_hours if config.general.cache_enabled else 0
    cache = MetadataCache(ttl)

    search_info = cache.get(search_url)
    if search_info is None:
        downloader = build_downloader(config)
        status_ctx = (
            console.status(f"Buscando '{escape(query)}'...") if not json_output else nullcontext()
        )
        with status_ctx:
            try:
                search_info = downloader.extract_metadata_only(search_url, flat=True)
            except (DownloadError, OSError) as exc:
                fail(f"La búsqueda falló: {exc}")
        cache.set(search_url, search_info)

    entries = [e for e in search_info.get("entries") or [] if e]
    results = [
        {
            "title": e.get("title"),
            "uploader": e.get("uploader") or e.get("channel"),
            "duration_seconds": e.get("duration"),
            "view_count": e.get("view_count"),
            "url": e.get("webpage_url") or e.get("url"),
        }
        for e in entries
    ]

    if json_output:
        console.print_json(data=results)
        return

    if not results:
        info("Sin resultados para tu búsqueda.")
        return

    table = Table(
        title=f"Resultados para: {escape(query)}",
        box=TABLE_BOX,
        header_style="header",
        border_style="border",
        title_style="title",
        row_styles=ZEBRA_ROW_STYLES,
    )
    table.add_column("#", justify="right", style="muted", width=3)
    table.add_column("Título", style="value", overflow="ellipsis", max_width=60)
    table.add_column("Canal", style="accent")
    table.add_column("Duración", justify="right")
    table.add_column("URL", style="url", overflow="fold")

    for i, row in enumerate(results, start=1):
        duration = row["duration_seconds"]
        duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else "?"
        table.add_row(
            str(i),
            escape(str(row["title"] or "?")),
            escape(str(row["uploader"] or "?")),
            duration_str,
            escape(str(row["url"] or "?")),
        )

    console.print(table)
    console.print("\n[muted]Para descargar un resultado: yt-cli download <URL>[/muted]")
