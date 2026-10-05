"""Configuración de logging estructurado.

En modo normal, solo se muestran mensajes claros de nivel WARNING+ vía Rich.
En modo `--debug`, se activa el nivel DEBUG con tracebacks completos.
"""

from __future__ import annotations

import logging

from rich.logging import RichHandler


def configure_logging(*, debug: bool) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    handler = RichHandler(
        show_time=debug,
        show_path=debug,
        rich_tracebacks=debug,
        markup=True,
    )
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[handler],
        force=True,
    )
