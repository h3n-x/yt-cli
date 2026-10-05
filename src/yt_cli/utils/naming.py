"""Construcción y sanitización de nombres de archivo a partir de plantillas.

Soporta placeholders: {title} {uploader} {date} {id} {playlist} {resolution}

El objetivo es producir nombres de archivo válidos simultáneamente en
Linux, macOS y Windows, incluso si los metadatos del video contienen
caracteres problemáticos (encabezados clickbait suelen incluir '|', '/', etc).
"""

from __future__ import annotations

import re
from string import Formatter
from typing import Any

# Caracteres prohibidos o problemáticos en Windows/macOS/Linux combinados.
# Una racha de caracteres inválidos consecutivos se reemplaza por un único
# `replacement` (p. ej. '"?' -> '_', no '__').
_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_TRAILING_DOTS_SPACES_RE = re.compile(r"[. ]+$")
_MULTIPLE_SPACES_RE = re.compile(r"\s+")

# Nombres reservados en Windows (case-insensitive), por si el destino se
# comparte luego con un sistema de archivos Windows/exFAT.
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

MAX_COMPONENT_LENGTH = 200  # deja margen para extensión + sufijos de desambiguación

SUPPORTED_PLACEHOLDERS = frozenset(
    {"title", "uploader", "date", "id", "playlist", "resolution", "ext"}
)


def sanitize_filename(name: str, *, replacement: str = "_") -> str:
    """Sanitiza un único componente de nombre (sin separadores de directorio)."""
    if not name:
        return "untitled"

    cleaned = _INVALID_CHARS_RE.sub(replacement, name)
    cleaned = _MULTIPLE_SPACES_RE.sub(" ", cleaned).strip()
    cleaned = _TRAILING_DOTS_SPACES_RE.sub("", cleaned)

    if not cleaned:
        return "untitled"

    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"

    if len(cleaned) > MAX_COMPONENT_LENGTH:
        cleaned = cleaned[:MAX_COMPONENT_LENGTH].rstrip()

    return cleaned


def sanitize_path_template_output(path_str: str) -> str:
    """Sanitiza cada componente de una ruta relativa (puede tener subdirectorios).

    Los separadores '/' definidos por la propia plantilla (p. ej.
    '{uploader}/{playlist}/{title}') se preservan como separadores de
    directorio; solo se sanitiza el contenido de cada componente.
    """
    parts = path_str.split("/")
    return "/".join(sanitize_filename(part) for part in parts if part != "")


def render_filename_template(template: str, context: dict[str, Any]) -> str:
    """Renderiza una plantilla tipo '{uploader}/{title}.{ext}' con `context`.

    Placeholders soportados: title, uploader, date, id, playlist, resolution, ext.
    Cualquier placeholder ausente en `context` se sustituye por 'unknown'
    en vez de lanzar una excepción, para que una descarga nunca falle solo
    por metadatos incompletos (p. ej. un video sin playlist asociada).
    """
    defaults = {
        "title": "untitled",
        "uploader": "unknown",
        "date": "unknown-date",
        "id": "unknown-id",
        "playlist": "no-playlist",
        "resolution": "unknown-res",
        "ext": "bin",
    }
    # Cada valor de metadatos se sanea ANTES de interpolarlo: un '/' en un
    # título ("AC/DC") no debe convertirse en un separador de directorio. Solo
    # los '/' escritos en la propia plantilla delimitan subdirectorios.
    safe_context = {
        key: sanitize_filename(str(context.get(key) or default))
        for key, default in defaults.items()
    }

    _check_template_syntax(template)

    try:
        rendered = template.format(**safe_context)
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Plantilla de nombre inválida: '{template}'") from exc

    return sanitize_path_template_output(rendered)


def _check_template_syntax(template: str) -> None:
    """Acepta solo placeholders simples (`{title}`): sin acceso a atributos
    (`{title.__class__}`), índices, conversiones (`!r`) ni especificadores de
    formato (`:>10`), que `str.format` admitiría pero que la traducción a la
    plantilla de yt-dlp no entiende.
    """
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as exc:
        raise ValueError(f"Plantilla de nombre inválida: '{template}' ({exc})") from exc

    for _literal, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in SUPPORTED_PLACEHOLDERS or format_spec or conversion:
            supported = ", ".join(f"{{{name}}}" for name in sorted(SUPPORTED_PLACEHOLDERS))
            raise ValueError(
                f"Placeholder no soportado '{{{field_name}}}' en '{template}'. "
                f"Usa solo: {supported}."
            )
