"""Tema visual centralizado para toda la CLI.

Este módulo es puramente estético: define la paleta de colores semánticos,
los iconos de estado, y algunas constantes de estilo (box de tablas, anchos)
reutilizadas por `cli/main.py` y `utils/progress_ui.py`. Centralizarlo aquí
evita que cada comando reinvente su propia combinación de colores y hace que
cambiar el "look" de la CLI sea un cambio en un solo archivo.

No contiene lógica de negocio: nada de aquí decide qué pasa con una
descarga, solo cómo se ve en pantalla.
"""

from __future__ import annotations

from rich import box
from rich.theme import Theme

from yt_cli.models.enums import DownloadStatus

# Paleta semántica: el resto del código usa nombres ("success", "error"...)
# en vez de colores hardcodeados ("green", "red"...), para poder retocar la
# paleta completa desde un solo lugar.
YT_CLI_THEME = Theme(
    {
        "success": "bold spring_green3",
        "error": "bold red3",
        "warning": "bold gold3",
        "info": "bold sky_blue2",
        "accent": "bold medium_orchid",
        "muted": "grey62",
        "title": "bold white",
        "header": "bold turquoise2",
        "border": "grey42",
        "value": "bold white",
        "url": "underline sky_blue2",
        "prompt": "bold gold3",
    }
)

# Icono asociado a cada estado de descarga, usado consistentemente en la
# barra de progreso, el historial y los resúmenes de colección.
STATUS_ICON: dict[DownloadStatus, str] = {
    DownloadStatus.QUEUED: "◌",
    DownloadStatus.DOWNLOADING: "↓",
    DownloadStatus.CONVERTING: "⚙",
    DownloadStatus.COMPLETED: "✓",
    DownloadStatus.PARTIAL: "◐",
    DownloadStatus.FAILED: "✗",
    DownloadStatus.CANCELLED: "⊘",
    DownloadStatus.SKIPPED: "⏭",
}

# Estilo del tema asociado a cada estado, para colorear el icono/texto.
STATUS_STYLE: dict[DownloadStatus, str] = {
    DownloadStatus.QUEUED: "muted",
    DownloadStatus.DOWNLOADING: "info",
    DownloadStatus.CONVERTING: "accent",
    DownloadStatus.COMPLETED: "success",
    DownloadStatus.PARTIAL: "warning",
    DownloadStatus.FAILED: "error",
    DownloadStatus.CANCELLED: "muted",
    DownloadStatus.SKIPPED: "warning",
}


def status_badge(status: DownloadStatus) -> str:
    """Devuelve el icono + estilo Rich listo para interpolar en un string,
    p. ej. `f"{status_badge(result.status)} {titulo}"`.
    """
    icon = STATUS_ICON.get(status, "•")
    style = STATUS_STYLE.get(status, "muted")
    return f"[{style}]{icon}[/{style}]"


# Box de tabla consistente en toda la CLI: bordes redondeados, más suaves
# visualmente que el ASCII por defecto de Rich.
TABLE_BOX = box.ROUNDED

# Colores alternos de fila ("zebra striping") para tablas largas
# (historial, búsqueda). Se usa "dim" en vez de un color de fondo: se ve bien
# tanto en terminales de tema claro como oscuro, sin asumir una paleta de
# fondo concreta.
ZEBRA_ROW_STYLES = ("", "dim")
