"""Cola de descargas concurrente.

`yt_dlp.YoutubeDL.extract_info` es una llamada bloqueante (I/O + CPU para
remux/postprocesado vía ffmpeg). Para lograr concurrencia real sin reescribir
yt-dlp de forma asíncrona, cada descarga se ejecuta en un hilo de un
`ThreadPoolExecutor` gestionado por asyncio, con un número de workers
configurable (`max_concurrent_downloads`). Esto da paralelismo efectivo
porque la mayor parte del tiempo se pasa en I/O de red o en el subproceso
ffmpeg, ambos liberando el GIL.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from yt_cli.core.downloader import DownloadResult, ProgressCallback, YtDlpDownloader
from yt_cli.models.download_request import DownloadRequest

ResultCallback = Callable[[DownloadResult], Awaitable[None] | None]


@dataclass(slots=True)
class QueueSummary:
    total: int
    completed: int
    failed: int


class DownloadQueue:
    """Ejecuta múltiples `DownloadRequest` con un límite de concurrencia."""

    def __init__(self, downloader: YtDlpDownloader, max_concurrent: int) -> None:
        self._downloader = downloader
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _run_one(
        self,
        request: DownloadRequest,
        progress_callback: ProgressCallback | None,
        on_result: ResultCallback | None,
    ) -> DownloadResult:
        async with self._semaphore:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, self._downloader.download, request, progress_callback
            )
            if on_result is not None:
                maybe_awaitable = on_result(result)
                if asyncio.iscoroutine(maybe_awaitable):
                    await maybe_awaitable
            return result

    async def run_all(
        self,
        requests: list[DownloadRequest],
        *,
        progress_callback_factory: Callable[[DownloadRequest], ProgressCallback | None] | None = None,
        on_result: ResultCallback | None = None,
    ) -> QueueSummary:
        tasks = [
            self._run_one(
                request,
                progress_callback_factory(request) if progress_callback_factory else None,
                on_result,
            )
            for request in requests
        ]
        results = await asyncio.gather(*tasks)

        completed = sum(1 for r in results if r.status.value == "completed")
        return QueueSummary(total=len(results), completed=completed, failed=len(results) - completed)
