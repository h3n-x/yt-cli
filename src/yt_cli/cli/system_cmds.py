"""`doctor`, `version`, `update` y `self-update`."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import sysconfig
from enum import Enum
from importlib.metadata import PackageNotFoundError, distribution
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from yt_cli.cli._app import EXIT_FAILURE, app, console, fail, success, warn
from yt_cli.config.manager import ConfigError, config_file_path, load_config
from yt_cli.core.dependencies import (
    JS_RUNTIME_BINARIES,
    STALE_YT_DLP_DAYS,
    find_js_runtime,
    has_mutagen,
    yt_dlp_version_info,
)
from yt_cli.utils.theme import TABLE_BOX, ZEBRA_ROW_STYLES

PACKAGE_NAME = "yt-cli"
# Un paquete de PyPI llamado "yt-cli" solo se considera una actualización
# legítima si declara este repositorio entre sus URLs de proyecto: el nombre
# por sí solo no prueba nada (cualquiera podría registrarlo).
PROJECT_SOURCE_URL = "https://github.com/h3n-x/yt-cli"


class Check(Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


_CHECK_ICON = {
    Check.OK: "[success]✓[/success]",
    Check.WARN: "[warning]⚠[/warning]",
    Check.FAIL: "[error]✗[/error]",
}


# ------------------------------------------------------------------ doctor


@app.command()
def doctor() -> None:
    """Verifica el entorno: ffmpeg, runtime JS, yt-dlp, mutagen, permisos y espacio."""
    checks: list[tuple[str, Check, str]] = []

    python_ok = sys.version_info >= (3, 13)
    checks.append(("Python", Check.OK if python_ok else Check.FAIL, sys.version.split()[0]))

    for binary in ("ffmpeg", "ffprobe"):
        found = shutil.which(binary) is not None
        detail = "instalado" if found else "no encontrado en PATH (sudo pacman -S ffmpeg)"
        checks.append((binary, Check.OK if found else Check.FAIL, detail))

    runtime = find_js_runtime()
    checks.append(
        (
            "runtime JavaScript",
            Check.OK if runtime else Check.FAIL,
            runtime
            or f"ninguno de {', '.join(JS_RUNTIME_BINARIES)}; "
            "YouTube lo exige (sudo pacman -S deno)",
        )
    )

    ytdlp = yt_dlp_version_info()
    if ytdlp is None:
        checks.append(("yt-dlp", Check.FAIL, "no instalado"))
    elif ytdlp.age_days is not None and ytdlp.age_days > STALE_YT_DLP_DAYS:
        checks.append(
            (
                "yt-dlp",
                Check.WARN,
                f"versión {ytdlp.version}, de hace {ytdlp.age_days} días: actualízalo "
                "(YouTube cambia a menudo)",
            )
        )
    else:
        checks.append(("yt-dlp", Check.OK, f"versión {ytdlp.version}"))

    checks.append(
        (
            "mutagen",
            Check.OK if has_mutagen() else Check.WARN,
            "instalado"
            if has_mutagen()
            else "falta: sin carátula en opus/ogg/flac (sudo pacman -S python-mutagen)",
        )
    )

    config_dir = config_file_path().parent
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        probe = config_dir / ".yt-cli-write-test"
        probe.write_text("ok")
        probe.unlink()
        checks.append(("directorio de config", Check.OK, str(config_file_path())))
    except OSError as exc:
        checks.append(("directorio de config", Check.FAIL, f"{config_dir}: {exc}"))

    try:
        cfg = load_config()
    except ConfigError as exc:
        checks.append(("configuración", Check.FAIL, str(exc)))
    else:
        checks.append(("configuración", Check.OK, "válida"))
        try:
            cfg.general.download_directory.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(cfg.general.download_directory)
        except OSError as exc:
            checks.append(("directorio de descarga", Check.FAIL, str(exc)))
        else:
            free_gib = usage.free / (1024**3)
            checks.append(
                (
                    "directorio de descarga",
                    Check.OK if free_gib >= 1 else Check.WARN,
                    f"{cfg.general.download_directory} ({free_gib:.1f} GiB libres)",
                )
            )

    table = Table(
        title="yt-cli doctor",
        box=TABLE_BOX,
        header_style="header",
        border_style="border",
        title_style="title",
        row_styles=ZEBRA_ROW_STYLES,
    )
    table.add_column("Componente", style="value")
    table.add_column("Estado", justify="center")
    table.add_column("Detalle", style="muted")
    for name, status, detail in checks:
        table.add_row(name, _CHECK_ICON[status], escape(detail))

    console.print(table)
    console.print(
        Panel(
            "Las URLs con '&', '?' o '=' deben ir siempre entre comillas, p. ej.:\n"
            '[value]yt-cli download "https://youtu.be/...&si=..."[/value]\n'
            "o el shell (zsh/bash) las interpretará como operadores en vez de "
            "pasarlas al programa.",
            title="💡 Tip",
            title_align="left",
            border_style="info",
            expand=False,
        )
    )
    if any(status is Check.FAIL for _, status, _ in checks):
        raise typer.Exit(code=EXIT_FAILURE)


# ------------------------------------------------------------------ versiones


def _current_version() -> str:
    try:
        return pkg_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.0.0+dev"


_VERSION_RE = re.compile(r"^\s*v?(?P<nums>\d+(?:\.\d+)*)(?P<rest>.*)$")
# Orden de las pre-releases según PEP 440: dev < alpha < beta < rc.
_PRERELEASE_RANK = (("dev", 0), ("alpha", 1), ("a", 1), ("beta", 2), ("b", 2), ("rc", 3), ("c", 3))


def _parse_version(value: str) -> tuple[int, ...]:
    """Convierte una versión ('1.2.3', '1.0.0rc1', '2.0.0-beta', '1.0+dev')
    en una tupla comparable: `(mayor, menor, parche, es_final, tipo_pre, n_pre)`.

    Una pre-release ordena antes que la versión final correspondiente
    ('1.0.0b2' < '1.0.0rc1' < '1.0.0'); la parte local ('+dev') se ignora. No
    se usa el paquete `packaging` para no añadir una dependencia de runtime
    por una única comparación.
    """
    match = _VERSION_RE.match(value.split("+", maxsplit=1)[0])
    if match is None:
        return (0, 0, 0, 0, 0, 0)
    numbers = [int(part) for part in match.group("nums").split(".")]
    numbers += [0] * (3 - len(numbers))
    rest = match.group("rest").strip(".-_").lower()
    if not rest:
        return (*numbers, 1, 0, 0)
    rank = next((r for prefix, r in _PRERELEASE_RANK if rest.startswith(prefix)), 2)
    pre_number = re.search(r"\d+", rest)
    return (*numbers, 0, rank, int(pre_number.group()) if pre_number else 0)


def _fetch_latest_pypi_version(package_name: str, timeout: float = 5.0) -> str:
    """Última versión publicada en PyPI de `package_name`, comprobando que el
    paquete pertenece a este proyecto.

    Lanza `LookupError` si no está publicado o si pertenece a otro proyecto,
    y `httpx.HTTPError` ante fallos de red.
    """
    import httpx  # import diferido: solo lo usan update/self-update

    response = httpx.get(
        f"https://pypi.org/pypi/{package_name}/json", timeout=timeout, follow_redirects=True
    )
    if response.status_code == 404:
        raise LookupError(f"El paquete '{package_name}' no está publicado en PyPI todavía.")
    response.raise_for_status()
    data = response.json()["info"]

    project_urls = [str(url) for url in (data.get("project_urls") or {}).values()]
    expected = PROJECT_SOURCE_URL.lower()
    if not any(url.rstrip("/").lower().startswith(expected) for url in project_urls):
        raise LookupError(
            f"El paquete '{package_name}' publicado en PyPI no pertenece a este proyecto "
            f"(no declara {PROJECT_SOURCE_URL}). Por seguridad no se usará para actualizar."
        )
    return str(data["version"])


def _installer() -> str | None:
    """Herramienta que instaló yt-cli según el archivo INSTALLER (PEP 376):
    'pip', 'uv', … o None si no se sabe (p. ej. paquete de pacman).
    """
    try:
        text = distribution(PACKAGE_NAME).read_text("INSTALLER")
    except PackageNotFoundError:
        return None
    return text.strip().lower() if text else None


def _is_externally_managed() -> bool:
    """True si el intérprete es el Python del sistema marcado por la distro
    como gestionado externamente (PEP 668), fuera de un entorno virtual.
    """
    in_venv = sys.prefix != sys.base_prefix
    marker = Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED"
    return not in_venv and marker.exists()


def _upgrade_hint(latest: str) -> str:
    installer = _installer()
    if installer == "uv":
        return "uv tool upgrade yt-cli"
    if installer == "pip" and not _is_externally_managed():
        return "yt-cli self-update"
    return (
        "actualiza con tu gestor de paquetes "
        f"(en Arch: paru -Syu yt-cli, o makepkg -si con v{latest})"
    )


@app.command()
def version(
    json_output: Annotated[
        bool, typer.Option("--json", help="Salida en formato JSON (para scripting).")
    ] = False,
) -> None:
    """Muestra la versión de yt-cli y sus dependencias clave."""
    versions: dict[str, str] = {"yt-cli": _current_version()}
    for dep in ("yt-dlp", "rich", "typer"):
        try:
            versions[dep] = pkg_version(dep)
        except PackageNotFoundError:
            versions[dep] = "no instalado"

    if json_output:
        console.print_json(data=versions)
        return

    body = Text()
    body.append("yt-cli ", style="title")
    body.append(versions["yt-cli"], style="accent")
    body.append("\n\n")
    for i, dep in enumerate(("yt-dlp", "rich", "typer")):
        if i:
            body.append("\n")
        body.append(f"{dep:>7}", style="muted")
        body.append(" · ")
        installed = versions[dep] != "no instalado"
        body.append(versions[dep], style="value" if installed else "error")

    console.print(Panel(body, border_style="border", expand=False, title="📦", title_align="left"))


def _latest_or_fail() -> str:
    import httpx

    try:
        return _fetch_latest_pypi_version(PACKAGE_NAME)
    except LookupError as exc:
        fail(str(exc))
    except httpx.HTTPError as exc:
        fail(
            "No se pudo comprobar la versión más reciente "
            f"(sin conexión o PyPI no disponible): {exc}"
        )


@app.command()
def update() -> None:
    """Comprueba si hay una versión más nueva de yt-cli publicada en PyPI (solo consulta)."""
    current = _current_version()
    latest = _latest_or_fail()

    if _parse_version(latest) > _parse_version(current):
        warn(f"Hay una versión nueva disponible: {latest} (tienes {current}).")
        console.print(f"Para actualizar: {escape(_upgrade_hint(latest))}")
    else:
        success(f"Ya tienes la última versión ({current}).")


@app.command(name="self-update")
def self_update(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="No pedir confirmación.")] = False,
) -> None:
    """Actualiza yt-cli vía pip, solo si fue instalado con pip en un entorno propio."""
    installer = _installer()
    if installer != "pip":
        fail(
            "yt-cli no se instaló con pip, así que self-update no puede actualizarlo de forma "
            f"segura. Para actualizar: {_upgrade_hint('X.Y.Z')}."
        )
    if _is_externally_managed():
        fail(
            "Este Python lo gestiona tu distribución (PEP 668); pip no debe modificarlo. "
            "Instala yt-cli con pipx/uv tool o con el paquete de tu distribución."
        )

    current = _current_version()
    latest = _latest_or_fail()

    if _parse_version(latest) <= _parse_version(current):
        success(f"Ya tienes la última versión ({current}).")
        return

    if not yes and not typer.confirm(f"¿Actualizar yt-cli de {current} a {latest}?"):
        console.print("Cancelado.")
        return

    # Lista de argumentos fija con el intérprete Python actual y versión exacta;
    # nunca se construye un comando de shell por concatenación (ver SECURITY.md).
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pip", "install", "--upgrade", f"{PACKAGE_NAME}=={latest}"],
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        fail("La actualización con pip falló (código distinto de cero). Revisa la salida anterior.")

    success(f"Actualizado a {latest}.")
