"""Cola de descargas concurrente.

`yt_dlp.YoutubeDL.extract_info` es una llamada bloqueante (I/O + CPU para
remux/postprocesado vía ffmpeg). Para lograr concurrencia real sin reescribir
yt-dlp de forma asíncrona, cada descarga se ejecuta en un hilo gestionado por
asyncio, con un número de descargas simultáneas configurable
(`max_concurrent_downloads`). Esto da paralelismo efectivo porque la mayor
parte del tiempo se pasa en I/O de red o en el subproceso ffmpeg, ambos
liberando el GIL.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import DownloadStatus
from yt_cli.models.results import DownloadResult, ProgressCallback

logger = logging.getLogger("yt_cli.queue")

ResultCallback = Callable[[int, DownloadResult], Awaitable[None] | None]


class Downloader(Protocol):
    def download(
        self, request: DownloadRequest, progress_callback: ProgressCallback | None = None
    ) -> DownloadResult: ...

    def cancel(self) -> None: ...


@dataclass(slots=True)
class QueueSummary:
    total: int
    completed: int
    failed: int
    cancelled: int = 0


class DownloadQueue:
    """Ejecuta múltiples `DownloadRequest` con un límite de concurrencia.

    Un fallo inesperado en una descarga se convierte en un resultado FAILED
    para esa entrada; nunca cancela el resto. Si la propia cola se cancela
    (Ctrl+C), se pide al downloader que detenga las descargas en curso para
    que los hilos terminen en segundos en vez de bloquear la salida.
    """

    def __init__(self, downloader: Downloader, max_concurrent: int) -> None:
        self._downloader = downloader
        self._max_concurrent = max_concurrent

    async def _run_one(
        self,
        index: int,
        request: DownloadRequest,
        semaphore: asyncio.Semaphore,
        progress_callback: ProgressCallback | None,
        on_result: ResultCallback | None,
    ) -> DownloadResult:
        async with semaphore:
            try:
                result = await asyncio.to_thread(
                    self._downloader.download, request, progress_callback
                )
            except Exception as exc:  # noqa: BLE001 - se aísla el fallo a esta entrada
                logger.debug("Fallo inesperado en %s", request.url, exc_info=True)
                result = DownloadResult(
                    request=request,
                    status=DownloadStatus.FAILED,
                    output_path=None,
                    title=None,
                    error_message=f"Error inesperado: {exc}",
                )
            if on_result is not None:
                maybe_awaitable = on_result(index, result)
                if asyncio.iscoroutine(maybe_awaitable):
                    await maybe_awaitable
            return result

    async def run_all(
        self,
        requests: list[DownloadRequest],
        *,
        progress_callback_factory: Callable[[int, DownloadRequest], ProgressCallback | None]
        | None = None,
        on_result: ResultCallback | None = None,
    ) -> QueueSummary:
        semaphore = asyncio.Semaphore(self._max_concurrent)
        try:
            async with asyncio.TaskGroup() as group:
                tasks = [
                    group.create_task(
                        self._run_one(
                            index,
                            request,
                            semaphore,
                            progress_callback_factory(index, request)
                            if progress_callback_factory
                            else None,
                            on_result,
                        )
                    )
                    for index, request in enumerate(requests)
                ]
        except asyncio.CancelledError:
            self._downloader.cancel()
            raise

        results = [task.result() for task in tasks]
        completed = sum(
            1 for r in results if r.status in (DownloadStatus.COMPLETED, DownloadStatus.PARTIAL)
        )
        cancelled = sum(1 for r in results if r.status is DownloadStatus.CANCELLED)
        return QueueSummary(
            total=len(results),
            completed=completed,
            failed=len(results) - completed - cancelled,
            cancelled=cancelled,
        )
