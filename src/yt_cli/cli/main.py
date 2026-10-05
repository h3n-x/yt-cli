"""Punto de entrada de la CLI: `yt-cli`.

Diseño de UX inspirado en git/uv/cargo/gh: subcomandos con verbos claros,
`--help` en todos los niveles, salida enriquecida vía Rich, y errores de
usuario (URL inválida, ffmpeg ausente, etc.) mostrados como mensajes claros
en vez de tracebacks, salvo que se pase `--debug`.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Annotated

import httpx
import typer
import yt_dlp.utils
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from yt_cli.config.manager import ConfigError, config_file_path, load_config, save_config
from yt_cli.config.models import AppConfig, DownloadDefaults
from yt_cli.core.converter import FFmpegNotFoundError
from yt_cli.core.downloader import DownloadError, DownloadResult, ProgressEvent, YtDlpDownloader
from yt_cli.core.validators import InvalidURLError, validate_urls
from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import AudioFormat, AudioQuality, DownloadKind, DownloadStatus, VideoFormat, VideoQuality
from yt_cli.services.cache import MetadataCache
from yt_cli.services.history import HistoryEntry, HistoryStore
from yt_cli.services.queue import DownloadQueue
from yt_cli.utils.logging import configure_logging
from yt_cli.utils.progress_ui import RichDownloadProgress
from yt_cli.utils.theme import STATUS_ICON, TABLE_BOX, YT_CLI_THEME, ZEBRA_ROW_STYLES, status_badge

app = typer.Typer(
    name="yt-cli",
    help="Descargador multimedia profesional para YouTube, pensado para Linux.",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
)

# Respeta el estándar NO_COLOR (https://no-color.org/) por accesibilidad: si la
# variable de entorno está definida (con cualquier valor no vacío), se desactivan
# los colores ANSI en toda la salida, incluidos los mensajes de error.
_NO_COLOR = bool(os.environ.get("NO_COLOR"))
console = Console(theme=YT_CLI_THEME, no_color=_NO_COLOR)
error_console = Console(stderr=True, theme=YT_CLI_THEME, no_color=_NO_COLOR)

@dataclass(slots=True)
class _CliState:
    debug: bool = False
    profile: str | None = None


state = _CliState()


def _fail(message: str, *, exit_code: int = 1) -> None:
    error_console.print(f"[error]✗ Error:[/error] {message}")
    raise typer.Exit(code=exit_code)


def _warn(message: str) -> None:
    console.print(f"[warning]⚠ {message}[/warning]")


def _success(message: str) -> None:
    console.print(f"[success]✓ {message}[/success]")


def _info(message: str) -> None:
    console.print(f"[info]ℹ {message}[/info]")


@app.callback()
def main(
    debug: Annotated[bool, typer.Option("--debug", help="Muestra tracebacks completos y logs DEBUG.")] = False,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Usa un perfil de descarga con nombre definido en config.toml."),
    ] = None,
    version_flag: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Muestra la versión y sale.",
            callback=lambda v: _version_callback(v),
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Opciones globales, aplicadas antes de cualquier subcomando."""
    state.debug = debug
    state.profile = profile
    configure_logging(debug=debug)


def _effective_downloads(config: AppConfig) -> DownloadDefaults:
    """Resuelve los valores de descarga por defecto: los del perfil pedido con
    `--profile`, o los globales de `[downloads]` si no se pidió ninguno.
    """
    try:
        return config.resolve_downloads(state.profile)
    except KeyError as exc:
        _fail(str(exc))
        raise  # _fail siempre lanza typer.Exit; esto solo satisface al type-checker


def _build_downloader(config: AppConfig) -> YtDlpDownloader:
    return YtDlpDownloader(
        max_concurrent_fragments=config.network.max_concurrent_fragments,
        retries=config.network.retries,
        proxy=config.network.proxy or None,
        rate_limit_kbps=config.network.rate_limit_kbps,
    )


def _build_request(
    url: str,
    kind: DownloadKind,
    *,
    output_dir: Path,
    filename_template: str,
    video_format: VideoFormat,
    audio_format: AudioFormat,
    video_quality: VideoQuality,
    audio_quality: AudioQuality,
    defaults: DownloadDefaults,
) -> DownloadRequest:
    return DownloadRequest(
        url=url,
        kind=kind,
        output_directory=output_dir,
        filename_template=filename_template,
        video_format=video_format,
        audio_format=audio_format,
        video_quality=video_quality,
        audio_quality=audio_quality,
        overwrite_policy=defaults.overwrite_policy,
        embed_thumbnail=defaults.embed_thumbnail,
        embed_metadata=defaults.embed_metadata,
        embed_chapters=defaults.embed_chapters,
        download_subtitles=defaults.download_subtitles,
        subtitle_languages=defaults.subtitle_languages,
    )


def _run_single_download(request: DownloadRequest) -> DownloadResult:
    config = load_config()
    downloader = _build_downloader(config)

    with RichDownloadProgress(console) as progress_ui:
        task_id = progress_ui.add_task(request.url)

        def on_progress(event: ProgressEvent) -> None:
            progress_ui.update(task_id, event)

        result = downloader.download(request, progress_callback=on_progress)
        progress_ui.finish(task_id, result)

    if config.general.history_enabled:
        HistoryStore().add(
            HistoryEntry(
                url=request.url,
                title=result.title,
                kind=request.kind,
                status=result.status,
                output_path=str(result.output_path) if result.output_path else None,
                error_message=result.error_message,
            )
        )

    return result


@app.command()
def download(
    url: Annotated[str, typer.Argument(help="URL del video de YouTube.")],
    format: Annotated[VideoFormat | None, typer.Option("--format", "-f", help="Formato de contenedor de salida.")] = None,
    quality: Annotated[VideoQuality | None, typer.Option("--quality", "-q", help="Calidad de video objetivo.")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Directorio de salida.")] = None,
    template: Annotated[str | None, typer.Option("--template", help="Plantilla de nombre de archivo.")] = None,
) -> None:
    """Descarga un único video."""
    config = load_config()
    defaults = _effective_downloads(config)
    try:
        request = _build_request(
            url,
            DownloadKind.VIDEO,
            output_dir=output or config.general.download_directory,
            filename_template=template or defaults.filename_template,
            video_format=format or defaults.video_format,
            audio_format=defaults.audio_format,
            video_quality=quality or defaults.video_quality,
            audio_quality=defaults.audio_quality,
            defaults=defaults,
        )
    except (InvalidURLError, ValueError) as exc:
        _fail(str(exc))
        return

    try:
        result = _run_single_download(request)
    except FFmpegNotFoundError as exc:
        _fail(str(exc))
        return

    if result.status is not DownloadStatus.COMPLETED:
        _fail(result.error_message or "La descarga falló por un motivo desconocido.")


@app.command()
def audio(
    url: Annotated[str, typer.Argument(help="URL del video de YouTube.")],
    format: Annotated[AudioFormat | None, typer.Option("--format", "-f", help="Formato de audio de salida.")] = None,
    quality: Annotated[AudioQuality | None, typer.Option("--quality", "-q", help="Bitrate objetivo.")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Directorio de salida.")] = None,
    template: Annotated[str | None, typer.Option("--template", help="Plantilla de nombre de archivo.")] = None,
) -> None:
    """Descarga solo el audio de un video, con conversión automática."""
    config = load_config()
    defaults = _effective_downloads(config)
    try:
        request = _build_request(
            url,
            DownloadKind.AUDIO,
            output_dir=output or config.general.download_directory,
            filename_template=template or defaults.filename_template,
            video_format=defaults.video_format,
            audio_format=format or defaults.audio_format,
            video_quality=defaults.video_quality,
            audio_quality=quality or defaults.audio_quality,
            defaults=defaults,
        )
    except (InvalidURLError, ValueError) as exc:
        _fail(str(exc))
        return

    try:
        result = _run_single_download(request)
    except FFmpegNotFoundError as exc:
        _fail(str(exc))
        return

    if result.status is not DownloadStatus.COMPLETED:
        _fail(result.error_message or "La descarga falló por un motivo desconocido.")


def _download_collection(url: str, kind: DownloadKind, output: Path | None, template: str | None) -> None:
    config = load_config()
    defaults = _effective_downloads(config)
    try:
        request = _build_request(
            url,
            kind,
            output_dir=output or config.general.download_directory,
            filename_template=template or defaults.playlist_filename_template,
            video_format=defaults.video_format,
            audio_format=defaults.audio_format,
            video_quality=defaults.video_quality,
            audio_quality=defaults.audio_quality,
            defaults=defaults,
        )
    except (InvalidURLError, ValueError) as exc:
        _fail(str(exc))
        return

    downloader = _build_downloader(config)

    console.rule(f"[header]{kind.value.capitalize()}[/header]", style="border")
    console.print(f"[muted]Extrayendo entradas de:[/muted] [url]{url}[/url]")
    with RichDownloadProgress(console) as progress_ui:
        task_id = progress_ui.add_task(url)

        def on_progress(event: ProgressEvent) -> None:
            progress_ui.update(task_id, event)

        summary, entry_results = downloader.download_collection(request, progress_callback=on_progress)
        progress_ui.finish(task_id, summary)

    if config.general.history_enabled:
        history = HistoryStore()
        if entry_results:
            # Una fila de historial por video de la colección, no una sola
            # fila agregada — permite ver exactamente qué entradas fallaron
            # (corrige B4 de AUDIT_REPORT.md).
            for entry_result in entry_results:
                history.add(
                    HistoryEntry(
                        url=request.url,
                        title=entry_result.title,
                        kind=request.kind,
                        status=entry_result.status,
                        output_path=str(entry_result.output_path) if entry_result.output_path else None,
                        error_message=entry_result.error_message,
                    )
                )
        else:
            history.add(
                HistoryEntry(
                    url=request.url,
                    title=summary.title,
                    kind=request.kind,
                    status=summary.status,
                    output_path=str(summary.output_path) if summary.output_path else None,
                    error_message=summary.error_message,
                )
            )

    if summary.status is DownloadStatus.FAILED:
        _fail(summary.error_message or "La descarga de la colección falló por completo.")
    elif summary.status is DownloadStatus.PARTIAL:
        console.print(
            f"[warning]{STATUS_ICON[DownloadStatus.PARTIAL]} Completado parcialmente:[/warning] "
            f"{summary.error_message} Revisa 'yt-cli history' para ver qué entradas fallaron."
        )
        raise typer.Exit(code=2)  # código distinto de 1 (fallo total) para distinguir éxito parcial
    else:
        entry_count = summary.entry_count or 1
        _success(f"{entry_count} {'entrada' if entry_count == 1 else 'entradas'} descargadas correctamente.")


@app.command()
def playlist(
    url: Annotated[str, typer.Argument(help="URL de la playlist de YouTube.")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    template: Annotated[str | None, typer.Option("--template")] = None,
) -> None:
    """Descarga una playlist completa."""
    _download_collection(url, DownloadKind.PLAYLIST, output, template)


@app.command()
def channel(
    url: Annotated[str, typer.Argument(help="URL del canal de YouTube.")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    template: Annotated[str | None, typer.Option("--template")] = None,
) -> None:
    """Descarga todos los videos públicos de un canal."""
    _download_collection(url, DownloadKind.CHANNEL, output, template)


@app.command()
def batch(
    file: Annotated[Path, typer.Argument(help="Archivo de texto con una URL por línea.")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    audio_only: Annotated[bool, typer.Option("--audio", help="Descargar solo audio para todas las URLs.")] = False,
) -> None:
    """Descarga en paralelo todas las URLs listadas en un archivo de texto."""
    if not file.exists():
        _fail(f"El archivo '{file}' no existe.")
        return

    raw_lines = [
        line.strip()
        for line in file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    try:
        urls = validate_urls(raw_lines)
    except InvalidURLError as exc:
        _fail(str(exc))
        return

    if not urls:
        _fail(f"'{file}' no contiene ninguna URL válida.")
        return

    config = load_config()
    defaults = _effective_downloads(config)
    kind = DownloadKind.AUDIO if audio_only else DownloadKind.VIDEO
    try:
        requests = [
            _build_request(
                u,
                kind,
                output_dir=output or config.general.download_directory,
                filename_template=defaults.filename_template,
                video_format=defaults.video_format,
                audio_format=defaults.audio_format,
                video_quality=defaults.video_quality,
                audio_quality=defaults.audio_quality,
                defaults=defaults,
            )
            for u in urls
        ]
    except ValueError as exc:
        _fail(str(exc))
        return

    downloader = _build_downloader(config)
    dqueue = DownloadQueue(downloader, max_concurrent=config.network.max_concurrent_downloads)
    history = HistoryStore() if config.general.history_enabled else None

    with RichDownloadProgress(console) as progress_ui:
        task_ids = {req.url: progress_ui.add_task(req.url) for req in requests}

        def progress_factory(req: DownloadRequest):
            def _cb(event: ProgressEvent) -> None:
                progress_ui.update(task_ids[req.url], event)

            return _cb

        def on_result(result: DownloadResult) -> None:
            progress_ui.finish(task_ids[result.request.url], result)
            if history is not None:
                history.add(
                    HistoryEntry(
                        url=result.request.url,
                        title=result.title,
                        kind=result.request.kind,
                        status=result.status,
                        output_path=str(result.output_path) if result.output_path else None,
                        error_message=result.error_message,
                    )
                )

        summary = asyncio.run(
            dqueue.run_all(requests, progress_callback_factory=progress_factory, on_result=on_result)
        )

    console.rule(style="border")
    summary_style = "success" if summary.failed == 0 else "warning"
    console.print(
        f"[{summary_style}]Resumen:[/{summary_style}] "
        f"[success]{summary.completed}[/success]/{summary.total} completadas"
        + (f", [error]{summary.failed}[/error] fallidas." if summary.failed else ".")
    )
    if summary.failed:
        raise typer.Exit(code=1)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Consulta de búsqueda.")],
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=50)] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Salida en formato JSON (para scripting).")] = False,
) -> None:
    """Busca videos en YouTube y muestra resultados en una tabla."""
    downloader = _build_downloader(load_config())
    search_url = f"ytsearch{limit}:{query}"

    status_ctx = console.status(f"Buscando '{query}'...") if not json_output else nullcontext()
    with status_ctx:
        try:
            info = downloader.extract_metadata_only(search_url)
        except (yt_dlp.utils.DownloadError, DownloadError, OSError) as exc:
            # Acotado a errores de red/extractor (B8 de AUDIT_REPORT.md): antes
            # se capturaba `Exception` genérico. NOTA: `extract_metadata_only`
            # puede lanzar tanto `yt_dlp.utils.DownloadError` (fallo interno de
            # yt-dlp) como nuestro propio `core.downloader.DownloadError`
            # (cuando yt-dlp devuelve info=None sin lanzar excepción); antes
            # solo se capturaba el primero, así que el segundo caso escapaba
            # como una excepción no controlada (bug encontrado al escribir
            # tests/test_cli.py::TestSearchJson::test_search_handles_extraction_failure).
            _fail(f"La búsqueda falló: {exc}")
            return

    entries = info.get("entries") or []

    if json_output:
        results = [
            {
                "title": e.get("title"),
                "uploader": e.get("uploader"),
                "duration_seconds": e.get("duration"),
                "view_count": e.get("view_count"),
                "url": e.get("webpage_url") or e.get("url"),
            }
            for e in entries
        ]
        console.print_json(data=results)
        return

    if not entries:
        _info("Sin resultados para tu búsqueda.")
        return

    table = Table(
        title=f"Resultados para: {query}",
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
    table.add_column("Vistas", justify="right")

    for i, entry in enumerate(entries, start=1):
        duration = entry.get("duration")
        duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else "?"
        views = entry.get("view_count")
        table.add_row(
            str(i),
            entry.get("title", "?"),
            entry.get("uploader", "?"),
            duration_str,
            f"{views:,}" if views else "?",
        )

    console.print(table)
    console.print(
        "\n[muted]Para descargar un resultado: yt-cli download <URL> "
        "(usa el enlace del video, no el número de esta tabla).[/muted]"
    )


config_app = typer.Typer(help="Gestiona la configuración persistente de yt-cli.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """Muestra la configuración actual (efectiva) en formato TOML."""
    cfg = load_config()
    console.rule("[header]Configuración[/header]", style="border")
    console.print(f"[muted]Archivo: {config_file_path()}[/muted]\n")
    console.print_json(data=cfg.model_dump(mode="json"))


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Clave con notación de puntos, ej: downloads.video_quality")],
    value: Annotated[str, typer.Argument(help="Nuevo valor.")],
) -> None:
    """Modifica un valor de configuración y lo persiste en disco."""
    cfg = load_config()
    parts = key.split(".")

    obj = cfg
    try:
        for part in parts[:-1]:
            obj = getattr(obj, part)
    except AttributeError:
        # Antes esto propagaba un AttributeError crudo hasta el usuario (sin
        # --debug); ahora se convierte en un mensaje claro, consistente con el
        # resto de la CLI.
        _fail(f"'{key}' no es una ruta de configuración válida. Usa 'yt-cli config show' para ver las claves.")
        return

    if not hasattr(obj, parts[-1]):
        _fail(f"'{key}' no es una ruta de configuración válida. Usa 'yt-cli config show' para ver las claves.")
        return

    try:
        setattr(obj, parts[-1], value)
    except (ValidationError, ValueError, TypeError) as exc:
        _fail(f"Valor inválido para '{key}': {exc}")
        return

    try:
        path = save_config(cfg)
    except ConfigError as exc:
        _fail(str(exc))
        return

    _success(f"'{key}' actualizado. Guardado en {path}")


@config_app.command("path")
def config_path() -> None:
    """Muestra la ruta del archivo de configuración."""
    console.print(str(config_file_path()))


profile_app = typer.Typer(help="Gestiona perfiles de descarga con nombre (usados con --profile).")
config_app.add_typer(profile_app, name="profile")


@profile_app.command("list")
def profile_list() -> None:
    """Lista los perfiles definidos en config.toml."""
    cfg = load_config()
    if not cfg.profiles:
        _info("No hay perfiles definidos. Crea uno con 'yt-cli config profile set'.")
        return

    table = Table(
        title="Perfiles de descarga",
        box=TABLE_BOX,
        header_style="header",
        border_style="border",
        title_style="title",
        row_styles=ZEBRA_ROW_STYLES,
    )
    table.add_column("Nombre", style="accent")
    table.add_column("Video", style="value")
    table.add_column("Audio", style="value")

    for name, defaults in sorted(cfg.profiles.items()):
        table.add_row(
            name,
            f"{defaults.video_format.value} / {defaults.video_quality.value}",
            f"{defaults.audio_format.value} / {defaults.audio_quality.value}",
        )
    console.print(table)


@profile_app.command("show")
def profile_show(name: Annotated[str, typer.Argument(help="Nombre del perfil.")]) -> None:
    """Muestra todos los valores de un perfil en formato JSON."""
    cfg = load_config()
    if name not in cfg.profiles:
        _fail(f"Perfil '{name}' no existe. Usa 'yt-cli config profile list' para ver los disponibles.")
        return
    console.print_json(data=cfg.profiles[name].model_dump(mode="json"))


@profile_app.command("set")
def profile_set(
    name: Annotated[str, typer.Argument(help="Nombre del perfil (se crea si no existe).")],
    key: Annotated[str, typer.Argument(help="Campo a modificar, ej: audio_format, video_quality.")],
    value: Annotated[str, typer.Argument(help="Nuevo valor.")],
) -> None:
    """Crea o modifica un campo de un perfil con nombre.

    Ejemplo: yt-cli config profile set archivo audio_format flac
    """
    cfg = load_config()
    defaults = cfg.profiles[name].model_copy(deep=True) if name in cfg.profiles else DownloadDefaults()

    if not hasattr(defaults, key):
        _fail(f"'{key}' no es un campo válido de perfil. Usa 'yt-cli config profile show {name}' para ver los campos.")
        return

    try:
        setattr(defaults, key, value)
    except (ValidationError, ValueError, TypeError) as exc:
        _fail(f"Valor inválido para '{key}': {exc}")
        return

    cfg.profiles[name] = defaults
    try:
        path = save_config(cfg)
    except ConfigError as exc:
        _fail(str(exc))
        return

    _success(f"Perfil '{name}.{key}' actualizado. Guardado en {path}")


@profile_app.command("remove")
def profile_remove(name: Annotated[str, typer.Argument(help="Nombre del perfil a eliminar.")]) -> None:
    """Elimina un perfil con nombre."""
    cfg = load_config()
    if name not in cfg.profiles:
        _fail(f"Perfil '{name}' no existe.")
        return

    del cfg.profiles[name]
    try:
        path = save_config(cfg)
    except ConfigError as exc:
        _fail(str(exc))
        return

    _success(f"Perfil '{name}' eliminado. Guardado en {path}")


history_app = typer.Typer(help="Historial de descargas.", invoke_without_command=True)
app.add_typer(history_app, name="history")


def _print_history_table(limit: int, *, json_output: bool = False) -> None:
    entries = HistoryStore().list_recent(limit=limit)

    if json_output:
        console.print_json(data=[e.model_dump(mode="json") for e in entries])
        return

    if not entries:
        _info("El historial está vacío.")
        return

    table = Table(
        title="Historial de descargas",
        box=TABLE_BOX,
        header_style="header",
        border_style="border",
        title_style="title",
        row_styles=ZEBRA_ROW_STYLES,
    )
    table.add_column("Fecha", style="muted")
    table.add_column("Tipo", style="accent")
    table.add_column("Estado")
    table.add_column("Título", style="value", overflow="ellipsis", max_width=45)
    table.add_column("Ruta", style="muted", overflow="ellipsis", max_width=35)

    for entry in entries:
        table.add_row(
            entry.timestamp.strftime("%Y-%m-%d %H:%M"),
            entry.kind.value,
            f"{status_badge(entry.status)} {entry.status.value}",
            entry.title or "?",
            entry.output_path or "-",
        )

    console.print(table)


@history_app.callback(invoke_without_command=True)
def history_default(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=500)] = 20,
    json_output: Annotated[bool, typer.Option("--json", help="Salida en formato JSON (para scripting).")] = False,
) -> None:
    """Muestra el historial de descargas recientes (comportamiento por defecto de `yt-cli history`)."""
    if ctx.invoked_subcommand is None:
        _print_history_table(limit, json_output=json_output)


@history_app.command("export")
def history_export(
    output: Annotated[Path, typer.Argument(help="Ruta del archivo de salida.")],
    format: Annotated[str, typer.Option("--format", "-f", help="'json' o 'csv'.")] = "json",
) -> None:
    """Exporta todo el historial de descargas a JSON o CSV."""
    if format not in ("json", "csv"):
        _fail("--format debe ser 'json' o 'csv'.")
        return

    store = HistoryStore()
    written = store.export_json(output) if format == "json" else store.export_csv(output)
    _success(f"Historial exportado a {written}")


@history_app.command("clear")
def history_clear(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmación.")] = False,
) -> None:
    """Elimina todo el historial de descargas."""
    if not yes and not typer.confirm("¿Eliminar todo el historial de descargas?"):
        console.print("Cancelado.")
        return
    HistoryStore().clear()
    _success("Historial eliminado.")


cache_app = typer.Typer(help="Gestiona la cache local de metadatos.")
app.add_typer(cache_app, name="cache")


@cache_app.command("stats")
def cache_stats() -> None:
    """Muestra el tamaño y número de entradas de la cache."""
    config = load_config()
    stats = MetadataCache(config.general.cache_ttl_hours).stats()
    console.print(f"Entradas: {stats.entry_count} · Tamaño: {stats.total_bytes / 1024:.1f} KiB")


@cache_app.command("clear")
def cache_clear() -> None:
    """Elimina todas las entradas de la cache."""
    config = load_config()
    removed = MetadataCache(config.general.cache_ttl_hours).clear()
    _success(f"{removed} entradas eliminadas.")


@app.command()
def doctor() -> None:
    """Verifica que el entorno tenga todo lo necesario (ffmpeg, ffprobe, permisos)."""
    checks: list[tuple[str, bool, str]] = []

    checks.append(("Python", sys.version_info >= (3, 13), f"{sys.version.split()[0]}"))

    for binary in ("ffmpeg", "ffprobe"):
        found = shutil.which(binary) is not None
        checks.append((binary, found, "instalado" if found else "no encontrado en PATH"))

    try:
        yt_dlp_version = pkg_version("yt-dlp")
        checks.append(("yt-dlp", True, f"versión {yt_dlp_version}"))
    except PackageNotFoundError:
        checks.append(("yt-dlp", False, "no instalado"))

    # Comprobación real de escritura (antes había una línea muerta que
    # siempre evaluaba a True sin comprobar nada: `x = ... or True`).
    config_dir = config_file_path().parent
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        probe = config_dir / ".yt-cli-write-test"
        probe.write_text("ok")
        probe.unlink()
        checks.append(("directorio de config", True, str(config_file_path())))
    except OSError as exc:
        checks.append(("directorio de config", False, f"{config_dir}: {exc}"))

    try:
        cfg = load_config()
    except ConfigError as exc:
        checks.append(("configuración", False, str(exc)))
    else:
        checks.append(("configuración", True, "válida"))
        try:
            cfg.general.download_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            checks.append(("directorio de descarga", False, str(exc)))
        else:
            usage = shutil.disk_usage(cfg.general.download_directory)
            free_gib = usage.free / (1024**3)
            checks.append(
                (
                    "directorio de descarga",
                    True,
                    f"{cfg.general.download_directory} ({free_gib:.1f} GiB libres)",
                )
            )

    table = Table(
        title="yt-cli doctor",
        box=TABLE_BOX,
        header_style="header",
        border_style="border",
        title_style="title",
        row_styles=ZEBRA_ROW_STYLES,
    )
    table.add_column("Componente", style="value")
    table.add_column("Estado", justify="center")
    table.add_column("Detalle", style="muted")

    all_ok = True
    for name, ok, detail in checks:
        all_ok = all_ok and ok
        icon = "[success]✓[/success]" if ok else "[error]✗[/error]"
        table.add_row(name, icon, detail)

    console.print(table)
    console.print(
        Panel(
            "Las URLs con '&', '?' o '=' deben ir siempre entre comillas, p. ej.:\n"
            '[value]yt-cli download "https://youtu.be/...&si=..."[/value]\n'
            "o el shell (zsh/bash) las interpretará como operadores en vez de "
            "pasarlas al programa.",
            title="💡 Tip",
            title_align="left",
            border_style="info",
            expand=False,
        )
    )
    if not all_ok:
        raise typer.Exit(code=1)


def _current_version() -> str:
    try:
        return pkg_version("yt-cli")
    except PackageNotFoundError:
        return "0.0.0+dev"


def _parse_version(value: str) -> tuple[int, ...]:
    """Convierte 'X.Y.Z' (con sufijos como '+dev' ignorados) en una tupla
    comparable. No se usa el paquete `packaging` para esta única comparación
    de semver simple, siguiendo la política de dependencias mínimas del
    proyecto (ver ARCHITECTURE.md: "toda dependencia debe justificarse").
    """
    core = value.split("+")[0].split("-")[0]
    parts = []
    for piece in core.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _fetch_latest_pypi_version(package_name: str, timeout: float = 5.0) -> str:
    """Consulta la API JSON de PyPI para obtener la última versión publicada.

    Lanza `LookupError` si el paquete no está publicado (404) y
    `httpx.HTTPError` ante cualquier otro fallo de red.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    if response.status_code == 404:
        raise LookupError(f"El paquete '{package_name}' no está publicado en PyPI todavía.")
    response.raise_for_status()
    return response.json()["info"]["version"]


@app.command()
def version(
    json_output: Annotated[bool, typer.Option("--json", help="Salida en formato JSON (para scripting).")] = False,
) -> None:
    """Muestra la versión de yt-cli y sus dependencias clave."""
    versions: dict[str, str] = {"yt-cli": _current_version()}

    for dep in ("yt-dlp", "rich", "typer"):
        try:
            versions[dep] = pkg_version(dep)
        except PackageNotFoundError:
            versions[dep] = "no instalado"

    if json_output:
        console.print_json(data=versions)
        return

    body = Text()
    body.append("yt-cli ", style="title")
    body.append(versions["yt-cli"], style="accent")
    body.append("\n\n")
    for i, dep in enumerate(("yt-dlp", "rich", "typer")):
        if i:
            body.append("\n")
        body.append(f"{dep:>7}", style="muted")
        body.append(" · ")
        installed = versions[dep] != "no instalado"
        body.append(versions[dep], style="value" if installed else "error")

    console.print(Panel(body, border_style="border", expand=False, title="📦", title_align="left"))


@app.command()
def update() -> None:
    """Comprueba si hay una versión más nueva de yt-cli disponible en PyPI.

    Solo consulta; no instala nada. Usa 'yt-cli self-update' para instalar.
    """
    current = _current_version()
    try:
        latest = _fetch_latest_pypi_version("yt-cli")
    except LookupError as exc:
        _fail(str(exc))
        return
    except httpx.HTTPError as exc:
        _fail(f"No se pudo comprobar la versión más reciente (sin conexión o PyPI no disponible): {exc}")
        return

    if _parse_version(latest) > _parse_version(current):
        _warn(f"Hay una versión nueva disponible: {latest} (tienes {current}).")
        console.print("Ejecuta 'yt-cli self-update' o 'pip install --upgrade yt-cli' para actualizar.")
    else:
        _success(f"Ya tienes la última versión ({current}).")


@app.command(name="self-update")
def self_update(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmación.")] = False,
) -> None:
    """Actualiza yt-cli a la última versión disponible en PyPI, vía pip."""
    current = _current_version()
    try:
        latest = _fetch_latest_pypi_version("yt-cli")
    except LookupError as exc:
        _fail(str(exc))
        return
    except httpx.HTTPError as exc:
        _fail(f"No se pudo comprobar la versión más reciente (sin conexión o PyPI no disponible): {exc}")
        return

    if _parse_version(latest) <= _parse_version(current):
        _success(f"Ya tienes la última versión ({current}).")
        return

    if not yes and not typer.confirm(f"¿Actualizar yt-cli de {current} a {latest}?"):
        console.print("Cancelado.")
        return

    # Lista de argumentos fija con el intérprete Python actual; nunca se
    # construye un comando de shell por concatenación (ver SECURITY.md).
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pip", "install", "--upgrade", "yt-cli"],
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        _fail("La actualización con pip falló (código distinto de cero). Revisa la salida anterior.")
        return

    _success(f"Actualizado a {latest}.")


def _version_callback(value: bool) -> None:
    if not value:
        return
    console.print(f"yt-cli {_current_version()}")
    raise typer.Exit()


if __name__ == "__main__":
    app()
