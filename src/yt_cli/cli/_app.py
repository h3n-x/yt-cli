"""Objetos compartidos por todos los módulos de comandos de la CLI.

Cada módulo `cli/*_cmds.py` registra sus comandos sobre `app` (definido aquí)
al importarse; `cli/main.py` los importa todos y expone el punto de entrada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import NoReturn

import typer
from rich.console import Console
from rich.markup import escape

from yt_cli.utils.theme import YT_CLI_THEME

# Códigos de salida documentados (ver man page, sección CÓDIGOS DE SALIDA).
EXIT_OK = 0
EXIT_FAILURE = 1
# 2 lo reserva Click/Typer para errores de uso (opción desconocida, etc.).
EXIT_PARTIAL = 3
EXIT_INTERRUPTED = 130

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
class CliState:
    debug: bool = False
    profile: str | None = None


state = CliState()


def fail(message: str, *, exit_code: int = EXIT_FAILURE) -> NoReturn:
    """Muestra un error (texto plano, nunca interpretado como markup) y sale."""
    error_console.print(f"[error]✗ Error:[/error] {escape(message)}")
    raise typer.Exit(code=exit_code)


def warn(message: str) -> None:
    console.print(f"[warning]⚠ {escape(message)}[/warning]")


def success(message: str) -> None:
    console.print(f"[success]✓ {escape(message)}[/success]")


def info(message: str) -> None:
    console.print(f"[info]ℹ {escape(message)}[/info]")
