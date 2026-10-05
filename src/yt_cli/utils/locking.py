"""Bloqueo de archivos entre procesos, vía `fcntl.flock` (POSIX/Linux).

Corrige B7 de AUDIT_REPORT.md: el patrón "leer todo → modificar → escribir todo"
usado por config/historial/cache es atómico dentro de un proceso, pero sin
coordinación entre procesos dos invocaciones concurrentes de `yt-cli` pueden
perder escrituras (TOCTOU). Este módulo serializa el ciclo completo
lectura-modificación-escritura con un lock exclusivo sobre un archivo
`.lock` companion, para que un segundo proceso espere en vez de pisar datos.

Deliberadamente no se usa una librería de terceros (p. ej. `filelock`) porque
`fcntl` cubre el 100% del caso de uso (un solo host Linux, sin necesidad de
locks distribuidos entre máquinas) y evita una dependencia nueva sin
justificación suficiente, siguiendo el estándar fijado en ARCHITECTURE.md.
"""

from __future__ import annotations

import fcntl
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO


@contextmanager
def exclusive_lock(target: Path, *, timeout_seconds: float = 10.0) -> Iterator[None]:
    """Adquiere un lock exclusivo asociado a `target` para la duración del bloque `with`.

    El lock se materializa en `target` con sufijo `.lock` (no en `target` mismo,
    para no interferir con lectores que abren el archivo de datos directamente).
    Bloquea hasta `timeout_seconds`; si no consigue el lock, lanza `TimeoutError`
    en vez de colgar el proceso indefinidamente (p. ej. ante un lock huérfano).
    """
    lock_path = target.with_suffix(target.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("w") as lock_file:
        _acquire_with_timeout(lock_file, timeout_seconds)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _acquire_with_timeout(lock_file: IO[str], timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"No se pudo adquirir el lock de '{lock_file.name}' tras "
                    f"{timeout_seconds}s. ¿Hay otra instancia de yt-cli colgada?"
                ) from None
            time.sleep(0.05)
