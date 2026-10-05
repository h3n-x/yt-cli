"""`yt-cli history …` y `yt-cli cache …`."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from yt_cli.cli._app import app, console, fail, info, success
from yt_cli.config.manager import ConfigError, load_config
from yt_cli.models.enums import DownloadStatus
from yt_cli.services.cache import MetadataCache
from yt_cli.services.history import HistoryError, HistoryStore
from yt_cli.utils.theme import TABLE_BOX, ZEBRA_ROW_STYLES, status_badge

history_app = typer.Typer(help="Historial de descargas.", invoke_without_command=True)
app.add_typer(history_app, name="history")

cache_app = typer.Typer(help="Gestiona la cache local de resultados de búsqueda.")
app.add_typer(cache_app, name="cache")


class ExportFormat(StrEnum):
    JSON = "json"
    CSV = "csv"


def _print_history_table(limit: int, *, json_output: bool, failed_only: bool) -> None:
    try:
        entries = HistoryStore().list_all()
    except HistoryError as exc:
        fail(str(exc))
    if failed_only:
        entries = [e for e in entries if e.status is DownloadStatus.FAILED]
    entries = entries[:limit]

    if json_output:
        console.print_json(data=[e.model_dump(mode="json") for e in entries])
        return

    if not entries:
        info("El historial está vacío." if not failed_only else "No hay descargas fallidas.")
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
    table.add_column(
        "Detalle" if failed_only else "Ruta", style="muted", overflow="ellipsis", max_width=45
    )

    for entry in entries:
        detail = entry.error_message if failed_only else entry.output_path
        table.add_row(
            entry.timestamp.strftime("%Y-%m-%d %H:%M"),
            entry.kind.value,
            f"{status_badge(entry.status)} {entry.status.value}",
            escape(entry.title or entry.url),
            escape(detail or "-"),
        )

    console.print(table)


@history_app.callback(invoke_without_command=True)
def history_default(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=500)] = 20,
    json_output: Annotated[
        bool, typer.Option("--json", help="Salida en formato JSON (para scripting).")
    ] = False,
    failed_only: Annotated[
        bool, typer.Option("--failed", help="Mostrar solo descargas fallidas, con su causa.")
    ] = False,
) -> None:
    """Muestra el historial de descargas recientes."""
    if ctx.invoked_subcommand is None:
        _print_history_table(limit, json_output=json_output, failed_only=failed_only)


@history_app.command("export")
def history_export(
    output: Annotated[Path, typer.Argument(help="Ruta del archivo de salida.")],
    format: Annotated[
        ExportFormat, typer.Option("--format", "-f", help="Formato de exportación.")
    ] = ExportFormat.JSON,
    force: Annotated[
        bool, typer.Option("--force", help="Sobrescribir el archivo si ya existe.")
    ] = False,
) -> None:
    """Exporta todo el historial de descargas a JSON o CSV."""
    if output.exists() and not force:
        fail(f"'{output}' ya existe. Usa --force para sobrescribirlo.")

    store = HistoryStore()
    try:
        written = (
            store.export_json(output) if format is ExportFormat.JSON else store.export_csv(output)
        )
    except HistoryError as exc:
        fail(str(exc))
    except OSError as exc:
        fail(f"No se pudo escribir '{output}': {exc}")
    success(f"Historial exportado a {written}")


@history_app.command("clear")
def history_clear(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmación.")] = False,
) -> None:
    """Elimina todo el historial de descargas."""
    if not yes and not typer.confirm("¿Eliminar todo el historial de descargas?"):
        console.print("Cancelado.")
        return
    HistoryStore().clear()
    success("Historial eliminado.")


def _cache() -> MetadataCache:
    try:
        config = load_config()
    except ConfigError as exc:
        fail(str(exc))
    return MetadataCache(config.general.cache_ttl_hours)


@cache_app.command("stats")
def cache_stats() -> None:
    """Muestra el tamaño y número de entradas de la cache."""
    stats = _cache().stats()
    console.print(f"Entradas: {stats.entry_count} · Tamaño: {stats.total_bytes / 1024:.1f} KiB")


@cache_app.command("clear")
def cache_clear() -> None:
    """Elimina todas las entradas de la cache."""
    removed = _cache().clear()
    success(f"{removed} entradas eliminadas.")
