"""Configuración de logging.

En modo normal solo se muestran mensajes WARNING+ de yt-cli. Los mensajes de
yt-dlp no se imprimen nunca directamente: el downloader los recoge y la CLI
muestra cada error una sola vez, ya traducido. Con `--debug` se ve todo
(incluido el log interno de yt-dlp) con tracebacks completos.
"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler


def configure_logging(*, debug: bool, console: Console | None = None) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    handler = RichHandler(
        console=console,
        show_time=debug,
        show_path=debug,
        rich_tracebacks=debug,
        # markup=False: los mensajes incluyen texto externo (errores de yt-dlp,
        # títulos de videos). Con markup, '[youtube]' desaparecía del mensaje
        # y un texto con '[/algo]' lanzaba MarkupError y abortaba la descarga.
        markup=False,
    )
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
        force=True,
    )
