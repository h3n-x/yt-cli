"""Validación de entradas del usuario.

Estas funciones son la primera línea de defensa contra:
- command injection (nunca se construyen comandos shell por concatenación)
- path traversal (rutas de salida se resuelven y se confinan a un directorio base)
- URLs maliciosas o no soportadas (esquema/host restringidos)

Ninguna función de este módulo ejecuta subprocesos ni depende de otras capas:
son puras y testeables.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from yt_cli.models.enums import Scope

ALLOWED_URL_SCHEMES = {"http", "https"}

# Dominios soportados por yt-dlp para el propósito de este CLI.
# Se mantiene una lista explícita en vez de aceptar "cualquier URL que yt-dlp entienda"
# para evitar que el usuario pase accidentalmente rutas locales (file://) u otros
# esquemas peligrosos a un proceso que termina invocando ffmpeg sobre esa ruta.
# Los subdominios (www., m., music.) se aceptan por la comprobación de sufijo.
ALLOWED_HOST_SUFFIXES = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
)

# Prefijos de ruta que identifican la página de un canal en YouTube.
_CHANNEL_PATH_PREFIXES = ("/@", "/channel/", "/c/", "/user/")


class InvalidURLError(ValueError):
    """La URL proporcionada no es válida o no está soportada."""


class UnsafePathError(ValueError):
    """La ruta resultante escaparía del directorio base permitido."""


def validate_url(raw_url: str) -> str:
    """Valida que `raw_url` sea una URL http(s) de un host soportado.

    Devuelve la URL normalizada (sin espacios). Lanza `InvalidURLError` si no
    cumple los requisitos. No se intenta "adivinar" ni reparar URLs malformadas:
    es preferible fallar de forma explícita.
    """
    candidate = raw_url.strip()
    if not candidate:
        raise InvalidURLError("La URL está vacía.")

    parsed = urlparse(candidate)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise InvalidURLError(
            f"Esquema no soportado: '{parsed.scheme or '(ninguno)'}'. Se esperaba http o https."
        )

    # `hostname` (no `netloc`) descarta credenciales y puerto y normaliza a
    # minúsculas: 'https://www.youtube.com:443/...' es válido, y
    # 'https://youtube.com@evil.com/' se evalúa por su host real (evil.com).
    try:
        hostname = parsed.hostname
        _ = parsed.port  # valida que el puerto, si lo hay, sea numérico
    except ValueError as exc:  # puerto no numérico, corchetes IPv6 mal formados
        raise InvalidURLError(f"La URL no tiene un host válido: {exc}") from exc
    if not hostname:
        raise InvalidURLError("La URL no tiene un host válido.")

    host = hostname.removeprefix("www.")
    if not any(host == suffix or host.endswith(f".{suffix}") for suffix in ALLOWED_HOST_SUFFIXES):
        raise InvalidURLError(
            f"Host no soportado: '{host}'. YT-CLI solo soporta YouTube en esta versión."
        )

    return candidate


def validate_urls(raw_urls: list[str]) -> list[str]:
    """Valida una lista de URLs, agregando el índice al error si alguna falla."""
    validated: list[str] = []
    for i, url in enumerate(raw_urls):
        try:
            validated.append(validate_url(url))
        except InvalidURLError as exc:
            raise InvalidURLError(f"URL #{i + 1} inválida ('{url}'): {exc}") from exc
    return validated


def detect_scope(url: str) -> Scope:
    """Deduce si una URL (ya validada) apunta a un video, una playlist o un canal.

    - `/playlist?list=…` y los álbumes de YouTube Music (`/browse/…`) son playlists.
    - `/watch?v=…&list=…` es un video concreto dentro de una lista: se descarga
      solo el video (mismo criterio que yt-dlp con `noplaylist`).
    - `/@nombre`, `/channel/…`, `/c/…` y `/user/…` son canales.
    """
    parsed = urlparse(url)
    path = parsed.path or "/"
    query = parse_qs(parsed.query)

    if path.startswith(_CHANNEL_PATH_PREFIXES):
        return Scope.CHANNEL
    if path.startswith("/browse/"):
        return Scope.PLAYLIST
    if "list" in query and "v" not in query:
        return Scope.PLAYLIST
    return Scope.SINGLE


def resolve_safe_path(base_dir: Path, relative: str) -> Path:
    """Resuelve `relative` dentro de `base_dir`, rechazando path traversal.

    Se usa para cualquier ruta derivada de una plantilla de nombre de archivo
    (que puede incluir metadatos del video, potencialmente hostiles si un
    título contiene secuencias como '../').
    """
    base_resolved = base_dir.expanduser().resolve()
    candidate = (base_resolved / relative).resolve()

    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise UnsafePathError(
            f"La ruta resultante '{candidate}' escapa del directorio base '{base_resolved}'."
        ) from exc

    return candidate
