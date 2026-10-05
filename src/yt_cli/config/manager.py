"""Carga y persistencia de la configuración en ~/.config/yt-cli/config.toml.

Usa `tomllib` (stdlib, solo lectura) para parsear y `tomli_w` para escribir,
evitando dependencias de terceros más pesadas para algo tan simple.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_dir
from pydantic import ValidationError

from yt_cli.config.models import AppConfig
from yt_cli.utils.locking import exclusive_lock


class ConfigError(RuntimeError):
    """Error irrecuperable al cargar o guardar la configuración."""


def config_dir() -> Path:
    return Path(user_config_dir("yt-cli", appauthor=False))


def config_file_path() -> Path:
    return config_dir() / "config.toml"


def _to_toml_compatible(data: dict[str, Any]) -> dict[str, Any]:
    """Convierte tipos no nativos de TOML (Path, etc.) a str recursivamente.

    TOML no tiene `null`: las claves con valor `None` se omiten y, al cargar,
    Pydantic les vuelve a asignar su valor por defecto (`None`).
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, dict):
            result[key] = _to_toml_compatible(value)
        elif isinstance(value, Path):
            result[key] = str(value)
        else:
            result[key] = value
    return result


def load_config(path: Path | None = None) -> AppConfig:
    """Carga la configuración desde disco, o devuelve los valores por defecto
    si el archivo no existe todavía (primer uso de la herramienta).
    """
    target = path or config_file_path()

    if not target.exists():
        return AppConfig()

    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"El archivo de configuración '{target}' tiene TOML inválido: {exc}"
        ) from exc

    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"La configuración en '{target}' no es válida:\n{exc}") from exc


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    """Persiste `config` como TOML de forma atómica (escribe a un archivo
    temporal y luego renombra, evitando corromper la config si el proceso
    se interrumpe a mitad de escritura).
    """
    target = path or config_file_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    data = _to_toml_compatible(config.model_dump(mode="python"))
    toml_bytes = tomli_w.dumps(data).encode("utf-8")

    with exclusive_lock(target):
        tmp_path = target.with_suffix(".toml.tmp")
        # 0600: la configuración puede contener credenciales (proxy con
        # usuario:contraseña); no debe ser legible por otros usuarios locales.
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(toml_bytes)
        os.chmod(tmp_path, 0o600)  # por si el archivo temporal ya existía
        tmp_path.replace(target)

    return target
