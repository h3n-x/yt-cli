"""Punto de entrada de la CLI: `yt-cli`.

Diseño de UX inspirado en git/uv/cargo/gh: subcomandos con verbos claros,
`--help` en todos los niveles, salida enriquecida vía Rich, y errores de
usuario (URL inválida, ffmpeg ausente, etc.) mostrados como mensajes claros
en vez de tracebacks, salvo que se pase `--debug`.

Los comandos viven en `cli/*_cmds.py` y se registran sobre `app` al
importarse. Los módulos pesados (yt-dlp, httpx, asyncio) se importan dentro de
los comandos que los usan, para que `--help`, `config` o `history` arranquen
rápido (y el autocompletado del shell, que ejecuta el programa en cada TAB).
"""

from __future__ import annotations

from typing import Annotated

import typer

from yt_cli.cli import (  # noqa: F401 - registran sus comandos en `app`
    config_cmds,
    download_cmds,
    history_cmds,
    system_cmds,
)
from yt_cli.cli._app import EXIT_INTERRUPTED, app, console, error_console, state
from yt_cli.cli.system_cmds import _current_version, _parse_version  # noqa: F401
from yt_cli.utils.logging import configure_logging

__all__ = ["app", "run"]


def _version_callback(value: bool) -> None:
    if not value:
        return
    console.print(f"yt-cli {_current_version()}")
    raise typer.Exit()


@app.callback()
def main(
    debug: Annotated[
        bool, typer.Option("--debug", help="Muestra tracebacks completos y el log de yt-dlp.")
    ] = False,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile", "-p", help="Usa un perfil de descarga con nombre definido en config.toml."
        ),
    ] = None,
    version_flag: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Muestra la versión y sale.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Opciones globales, aplicadas antes de cualquier subcomando."""
    state.debug = debug
    state.profile = profile
    configure_logging(debug=debug, console=error_console)


def run() -> None:
    """Entry point de `yt-cli`: convierte Ctrl+C en una salida limpia (130)
    en vez de un traceback.
    """
    try:
        app()
    except KeyboardInterrupt:
        error_console.print("\n[warning]Interrumpido por el usuario.[/warning]")
        raise SystemExit(EXIT_INTERRUPTED) from None


if __name__ == "__main__":
    run()
