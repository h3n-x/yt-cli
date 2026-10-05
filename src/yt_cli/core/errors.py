"""Traducción de los errores de yt-dlp a mensajes accionables.

yt-dlp reporta los fallos como texto libre ("ERROR: [youtube] ID: Video
unavailable"). Aquí se limpian (prefijos, códigos ANSI) y se asocia a los
casos más frecuentes una pista concreta de qué puede hacer el usuario.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PREFIX_RE = re.compile(r"^\s*ERROR:\s*")
# "[youtube] eRGbT2uxj4g: Video unavailable" → id y causa
_EXTRACTOR_RE = re.compile(
    r"^\[(?P<extractor>[\w:.-]+)\]\s+(?P<id>[\w-]+):\s*(?P<reason>.*)$", re.S
)

# (fragmento a buscar en minúsculas, pista para el usuario)
_HINTS: tuple[tuple[str, str], ...] = (
    (
        "sign in to confirm you",
        "YouTube pide verificar que no eres un bot. Configura las cookies de tu navegador: "
        "yt-cli config set network.cookies_from_browser firefox",
    ),
    (
        "sign in to confirm your age",
        "Video con restricción de edad: configura network.cookies_from_browser con una "
        "sesión iniciada en YouTube.",
    ),
    (
        "members-only",
        "Contenido exclusivo para miembros del canal: requiere cookies de una cuenta con acceso.",
    ),
    (
        "private video",
        "El video es privado; solo su propietario puede verlo.",
    ),
    (
        "not available in your country",
        "Bloqueado en tu región. Puedes configurar un proxy: yt-cli config set network.proxy <url>",
    ),
    (
        "video unavailable",
        "El video fue eliminado, es privado o no está disponible en tu región.",
    ),
    (
        "requested format is not available",
        "La calidad/formato pedido no existe para este video; prueba con --quality best.",
    ),
    (
        "javascript runtime",
        "Instala un runtime JavaScript para que yt-dlp resuelva los retos de YouTube: "
        "sudo pacman -S deno",
    ),
    (
        "ffmpeg not found",
        "Instala ffmpeg: sudo pacman -S ffmpeg",
    ),
    (
        "mutagen",
        "Instala mutagen para incrustar carátulas en opus/ogg/flac: sudo pacman -S python-mutagen",
    ),
    (
        "http error 403",
        "YouTube rechazó la descarga (403). Suele resolverse actualizando yt-dlp.",
    ),
)


@dataclass(frozen=True, slots=True)
class ExplainedError:
    message: str
    video_id: str | None = None
    hint: str | None = None

    def __str__(self) -> str:
        return f"{self.message} — {self.hint}" if self.hint else self.message


def clean_message(raw: str) -> str:
    """Quita códigos ANSI y el prefijo 'ERROR:' de un mensaje de yt-dlp."""
    return _PREFIX_RE.sub("", _ANSI_RE.sub("", raw)).strip()


def explain(raw: str) -> ExplainedError:
    """Limpia un error de yt-dlp y le asocia una pista si se reconoce."""
    message = clean_message(raw)
    video_id = None
    match = _EXTRACTOR_RE.match(message)
    if match:
        video_id = match.group("id")
        message = f"{video_id}: {match.group('reason').strip()}"

    lowered = message.lower()
    hint = next((text for needle, text in _HINTS if needle in lowered), None)
    return ExplainedError(message=message, video_id=video_id, hint=hint)
