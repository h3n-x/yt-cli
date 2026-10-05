"""Capa de presentación: traduce `ProgressEvent`/`DownloadResult` a una
barra de progreso Rich con velocidad, ETA y tamaño, similar a la UX de
herramientas como `cargo build` o `docker pull`.

Puramente visual: este módulo no decide el estado de una descarga, solo
cómo se dibuja. Los colores e iconos vienen de `utils/theme.py`, para que
toda la CLI comparta una única paleta.
"""

from __future__ import annotations

from rich.console import Console
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

from yt_cli.core.downloader import DownloadResult, ProgressEvent
from yt_cli.models.enums import DownloadStatus
from yt_cli.utils.theme import STATUS_ICON, status_badge


class RichDownloadProgress:
    """Context manager que agrupa una o varias descargas en una única vista
    de progreso Rich (una barra por URL, actualizada en tiempo real).
    """

    def __init__(self, console: Console) -> None:
        self._progress = Progress(
            SpinnerColumn(style="info"),
            TextColumn("[value]{task.fields[label]}", justify="left"),
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
        self._console = console

    def __enter__(self) -> RichDownloadProgress:
        self._progress.__enter__()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._progress.__exit__(*exc_info)

    def add_task(self, url: str) -> TaskID:
        label = url if len(url) <= 60 else f"{url[:57]}..."
        return self._progress.add_task(label, total=None, label=label)

    def update(self, task_id: TaskID, event: ProgressEvent) -> None:
        if event.filename:
            short_name = event.filename.rsplit("/", maxsplit=1)[-1]
            self._progress.update(task_id, label=short_name)

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
            self._progress.update(task_id, description=f"[accent]{icon} Convirtiendo…[/accent]")

    def finish(self, task_id: TaskID, result: DownloadResult) -> None:
        if result.status is DownloadStatus.COMPLETED:
            label = result.title or (result.output_path.name if result.output_path else "completado")
            self._progress.update(
                task_id, label=f"{status_badge(result.status)} {label}", completed=100, total=100
            )
        elif result.status is DownloadStatus.PARTIAL:
            label = result.title or result.request.url
            self._progress.update(
                task_id,
                label=(
                    f"{status_badge(result.status)} {label} "
                    f"([warning]{result.entry_failures}/{result.entry_count} fallaron[/warning])"
                ),
                completed=100,
                total=100,
            )
        else:
            label = result.request.url
            self._progress.update(
                task_id,
                label=f"{status_badge(result.status)} {label}: [error]{result.error_message}[/error]",
            )
