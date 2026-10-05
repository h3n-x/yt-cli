"""Capa de presentación: traduce `ProgressEvent`/`DownloadResult` a una
barra de progreso Rich con velocidad, ETA y tamaño, similar a la UX de
herramientas como `cargo build` o `docker pull`.

Puramente visual: este módulo no decide el estado de una descarga, solo
cómo se dibuja. Todo texto de origen externo (títulos, nombres de archivo,
URLs, mensajes de error) se escapa antes de interpolarse en markup de Rich.
"""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from yt_cli.models.enums import DownloadStatus
from yt_cli.models.results import DownloadResult, ProgressEvent
from yt_cli.utils.theme import STATUS_ICON, status_badge

_MAX_LABEL = 60


def _shorten(text: str, limit: int = _MAX_LABEL) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


class RichDownloadProgress:
    """Context manager que agrupa una o varias descargas en una única vista
    de progreso Rich (una barra por URL, actualizada en tiempo real).
    """

    def __init__(self, console: Console) -> None:
        self._progress = Progress(
            SpinnerColumn(style="info"),
            TextColumn("{task.fields[label]}", justify="left"),
            BarColumn(
                bar_width=32,
                complete_style="info",
                finished_style="success",
                pulse_style="accent",
            ),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%", style="muted"),
            TextColumn("•", style="border"),
            DownloadColumn(),
            TextColumn("•", style="border"),
            TransferSpeedColumn(),
            TextColumn("•", style="border"),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        )

    def __enter__(self) -> RichDownloadProgress:
        self._progress.__enter__()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._progress.stop()

    def add_task(self, url: str) -> TaskID:
        label = f"[value]{escape(_shorten(url))}[/value]"
        return self._progress.add_task("", total=None, label=label)

    def update(self, task_id: TaskID, event: ProgressEvent) -> None:
        if event.filename:
            short_name = _shorten(event.filename.rsplit("/", maxsplit=1)[-1])
            position = ""
            if event.playlist_index and event.playlist_count:
                position = f"[muted]{event.playlist_index}/{event.playlist_count}[/muted] "
            self._progress.update(task_id, label=f"{position}[value]{escape(short_name)}[/value]")

        if event.total_bytes:
            self._progress.update(
                task_id,
                total=event.total_bytes,
                completed=event.downloaded_bytes or 0,
            )
        elif event.percent is not None:
            self._progress.update(task_id, total=100, completed=event.percent)

        if event.status is DownloadStatus.CONVERTING:
            icon = STATUS_ICON[DownloadStatus.CONVERTING]
            self._progress.update(task_id, label=f"[accent]{icon} Convirtiendo…[/accent]")

    def finish(self, task_id: TaskID, result: DownloadResult) -> None:
        """Deja la barra en su estado final. El detalle de los errores no se
        muestra aquí (se informa una sola vez en el resumen de la CLI).
        """
        badge = status_badge(result.status)
        name = result.title or (
            result.output_path.name if result.output_path else result.request.url
        )
        label = f"{badge} [value]{escape(_shorten(name))}[/value]"

        if result.status is DownloadStatus.COMPLETED:
            self._progress.update(task_id, label=label, completed=100, total=100)
        elif result.status is DownloadStatus.PARTIAL:
            label += f" [warning]({result.entry_failures}/{result.entry_count} fallaron)[/warning]"
            self._progress.update(task_id, label=label, completed=100, total=100)
        else:
            self._progress.update(task_id, label=label)
