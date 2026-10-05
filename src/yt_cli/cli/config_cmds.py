"""`yt-cli config …` y `yt-cli config profile …`."""

from __future__ import annotations

import tomllib
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

import typer
from pydantic import BaseModel, ValidationError
from rich.markup import escape
from rich.table import Table

from yt_cli.cli._app import app, console, fail, info, success
from yt_cli.config.manager import ConfigError, config_file_path, load_config, save_config
from yt_cli.config.models import AppConfig, DownloadDefaults
from yt_cli.utils.theme import TABLE_BOX, ZEBRA_ROW_STYLES

config_app = typer.Typer(help="Gestiona la configuración persistente de yt-cli.")
app.add_typer(config_app, name="config")

profile_app = typer.Typer(help="Gestiona perfiles de descarga con nombre (usados con --profile).")
config_app.add_typer(profile_app, name="profile")

_NULL_VALUES = {"", "none", "null"}


def _load() -> AppConfig:
    try:
        return load_config()
    except ConfigError as exc:
        fail(str(exc))


def _save(cfg: AppConfig) -> str:
    try:
        return str(save_config(cfg))
    except (ConfigError, OSError) as exc:
        fail(str(exc))


def _mask_secret_url(value: str | None) -> str | None:
    """Oculta 'usuario:contraseña@' de una URL de proxy al mostrarla."""
    if not value:
        return value
    parts = urlsplit(value)
    if parts.username is None and parts.password is None:
        return value
    host = parts.hostname or ""
    netloc = f"***:***@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _parse_raw_value(value: str) -> Any:
    """Convierte el texto de la línea de comandos en un valor tipado para las
    opciones libres de `[ytdlp]` (números, booleanos, listas en sintaxis TOML).
    """
    try:
        return tomllib.loads(f"v = {value}")["v"]
    except tomllib.TOMLDecodeError:
        return value


def _set_field(model: BaseModel, key: str, value: str) -> None:
    field = type(model).model_fields.get(key)
    if field is None:
        raise AttributeError(key)
    parsed: Any = value
    if value.strip().lower() in _NULL_VALUES and not field.is_required():
        parsed = field.get_default(call_default_factory=True)
    setattr(model, key, parsed)


@config_app.command("show")
def config_show() -> None:
    """Muestra la configuración actual (efectiva) en formato JSON."""
    cfg = _load()
    data = cfg.model_dump(mode="json")
    data["network"]["proxy"] = _mask_secret_url(data["network"].get("proxy"))
    console.rule("[header]Configuración[/header]", style="border")
    console.print(f"[muted]Archivo: {escape(str(config_file_path()))}[/muted]\n")
    console.print_json(data=data)


@config_app.command("set")
def config_set(
    key: Annotated[
        str,
        typer.Argument(help="Clave con notación de puntos, ej: downloads.video_quality"),
    ],
    value: Annotated[
        str,
        typer.Argument(help="Nuevo valor. 'none' restablece el valor por defecto."),
    ],
) -> None:
    """Modifica un valor de configuración y lo persiste en disco."""
    cfg = _load()
    section, _, field_name = key.partition(".")
    invalid = (
        f"'{key}' no es una ruta de configuración válida. "
        "Usa 'yt-cli config show' para ver las claves."
    )
    if not field_name or "." in field_name:
        fail(invalid)

    if section == "ytdlp":
        if value.strip().lower() in _NULL_VALUES:
            cfg.ytdlp.pop(field_name, None)
        else:
            cfg.ytdlp[field_name] = _parse_raw_value(value)
    else:
        target = getattr(cfg, section, None)
        if not isinstance(target, BaseModel):
            fail(invalid)
        try:
            _set_field(target, field_name, value)
        except AttributeError:
            fail(invalid)
        except (ValidationError, ValueError, TypeError) as exc:
            fail(f"Valor inválido para '{key}': {exc}")

    path = _save(cfg)
    success(f"'{key}' actualizado. Guardado en {path}")


@config_app.command("path")
def config_path() -> None:
    """Muestra la ruta del archivo de configuración."""
    # soft_wrap evita que Rich parta la ruta en varias líneas en terminales
    # estrechas (o en la salida capturada), lo que la haría inutilizable.
    console.print(str(config_file_path()), soft_wrap=True, highlight=False, markup=False)


@profile_app.command("list")
def profile_list() -> None:
    """Lista los perfiles definidos en config.toml."""
    cfg = _load()
    if not cfg.profiles:
        info("No hay perfiles definidos. Crea uno con 'yt-cli config profile set'.")
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
            escape(name),
            f"{defaults.video_format.value} / {defaults.video_quality.value}",
            f"{defaults.audio_format.value} / {defaults.audio_quality.value}",
        )
    console.print(table)


@profile_app.command("show")
def profile_show(name: Annotated[str, typer.Argument(help="Nombre del perfil.")]) -> None:
    """Muestra todos los valores de un perfil en formato JSON."""
    cfg = _load()
    if name not in cfg.profiles:
        fail(
            f"Perfil '{name}' no existe. Usa 'yt-cli config profile list' para ver los disponibles."
        )
    console.print_json(data=cfg.profiles[name].model_dump(mode="json"))


@profile_app.command("set")
def profile_set(
    name: Annotated[str, typer.Argument(help="Nombre del perfil (se crea si no existe).")],
    key: Annotated[str, typer.Argument(help="Campo a modificar, ej: audio_format, video_quality.")],
    value: Annotated[str, typer.Argument(help="Nuevo valor.")],
) -> None:
    """Crea o modifica un campo de un perfil con nombre.

    Ejemplo: yt-cli config profile set musica audio_format opus
    """
    cfg = _load()
    defaults = (
        cfg.profiles[name].model_copy(deep=True) if name in cfg.profiles else DownloadDefaults()
    )

    try:
        _set_field(defaults, key, value)
    except AttributeError:
        fail(
            f"'{key}' no es un campo válido de perfil. "
            f"Usa 'yt-cli config profile show {name}' para ver los campos."
        )
    except (ValidationError, ValueError, TypeError) as exc:
        fail(f"Valor inválido para '{key}': {exc}")

    cfg.profiles[name] = defaults
    path = _save(cfg)
    success(f"Perfil '{name}.{key}' actualizado. Guardado en {path}")


@profile_app.command("remove")
def profile_remove(
    name: Annotated[str, typer.Argument(help="Nombre del perfil a eliminar.")],
) -> None:
    """Elimina un perfil con nombre."""
    cfg = _load()
    if name not in cfg.profiles:
        fail(f"Perfil '{name}' no existe.")

    del cfg.profiles[name]
    path = _save(cfg)
    success(f"Perfil '{name}' eliminado. Guardado en {path}")
