"""Historial de descargas persistente en ~/.local/share/yt-cli/history.json.

Se usa un único archivo JSON (vía orjson, por rendimiento) en vez de SQLite:
el volumen esperado (historial personal de descargas) no justifica un motor
de base de datos, y JSON permite inspección/edición manual trivial por el
usuario. Si el proyecto necesitara consultas complejas en el futuro, este
módulo es el único punto que habría que migrar a SQLite (ver ROADMAP.md).
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from pathlib import Path

import orjson
from platformdirs import user_data_dir
from pydantic import BaseModel, Field, ValidationError

from yt_cli.models.enums import DownloadKind, DownloadStatus
from yt_cli.models.results import DownloadResult, EntryResult
from yt_cli.utils.locking import exclusive_lock


class HistoryError(RuntimeError):
    """El archivo de historial existe pero no se puede leer (JSON corrupto o
    filas que no cumplen el esquema).
    """


class HistoryEntry(BaseModel):
    url: str
    title: str | None
    kind: DownloadKind
    status: DownloadStatus
    output_path: str | None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_message: str | None = None

    @classmethod
    def from_result(cls, result: DownloadResult) -> HistoryEntry:
        """Fila de historial para una descarga individual (o el resumen de una
        colección que no expone entradas).
        """
        return cls(
            url=result.request.url,
            title=result.title,
            kind=result.request.kind,
            status=result.status,
            output_path=str(result.output_path) if result.output_path else None,
            error_message=result.error_message,
        )

    @classmethod
    def from_entry(cls, entry: EntryResult, result: DownloadResult) -> HistoryEntry:
        """Fila de historial para un video concreto de una playlist/canal: usa
        la URL del video (no la de la colección) para poder identificarlo.
        """
        media_kind = DownloadKind(result.request.media.value)
        return cls(
            url=entry.url or result.request.url,
            title=entry.title,
            kind=media_kind,
            status=entry.status,
            output_path=str(entry.output_path) if entry.output_path else None,
            error_message=entry.error_message,
        )

    @classmethod
    def rows_for(cls, result: DownloadResult) -> list[HistoryEntry]:
        """Todas las filas que genera un resultado: una por entrada en las
        colecciones, una sola en las descargas individuales.
        """
        if result.entries:
            return [cls.from_entry(entry, result) for entry in result.entries]
        return [cls.from_result(result)]


def history_file_path() -> Path:
    return Path(user_data_dir("yt-cli", appauthor=False)) / "history.json"


class HistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or history_file_path()

    def _read_all(self) -> list[HistoryEntry]:
        if not self._path.exists():
            return []
        try:
            raw = orjson.loads(self._path.read_bytes())
            return [HistoryEntry.model_validate(item) for item in raw]
        except (orjson.JSONDecodeError, ValidationError, TypeError) as exc:
            raise HistoryError(
                f"El historial '{self._path}' está dañado y no se puede leer: {exc}. "
                "Renómbralo o bórralo para empezar uno nuevo."
            ) from exc

    def _write_all(self, entries: list[HistoryEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = orjson.dumps(
            [entry.model_dump(mode="json") for entry in entries],
            option=orjson.OPT_INDENT_2,
        )
        tmp_path = self._path.with_suffix(".json.tmp")
        tmp_path.write_bytes(payload)
        tmp_path.replace(self._path)

    def add(self, entry: HistoryEntry) -> None:
        self.add_many([entry])

    def add_many(self, new_entries: list[HistoryEntry]) -> None:
        """Añade varias filas con una sola lectura y escritura del archivo
        (una playlist de N videos ya no reescribe el historial N veces).

        El lock envuelve TODO el ciclo lectura-modificación-escritura: dos
        procesos que añadan casi a la vez deben serializarse antes de leer, o
        el segundo pisaría las filas del primero.
        """
        if not new_entries:
            return
        with exclusive_lock(self._path):
            entries = self._read_all()
            entries.extend(new_entries)
            self._write_all(entries)

    def list_recent(self, limit: int = 50) -> list[HistoryEntry]:
        entries = self.list_all()
        return entries[:limit]

    def list_all(self) -> list[HistoryEntry]:
        """Todas las entradas, ordenadas de la más reciente a la más antigua."""
        return sorted(self._read_all(), key=lambda e: e.timestamp, reverse=True)

    def clear(self) -> None:
        with exclusive_lock(self._path):
            self._write_all([])

    def export_json(self, destination: Path) -> Path:
        """Exporta todo el historial como un array JSON legible por humanos."""
        entries = self.list_all()
        destination.write_bytes(
            orjson.dumps([e.model_dump(mode="json") for e in entries], option=orjson.OPT_INDENT_2)
        )
        return destination

    def export_csv(self, destination: Path) -> Path:
        """Exporta todo el historial como CSV (una fila por descarga)."""
        entries = self.list_all()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["timestamp", "kind", "status", "title", "url", "output_path", "error_message"]
        )
        for e in entries:
            writer.writerow(
                [
                    e.timestamp.isoformat(),
                    e.kind.value,
                    e.status.value,
                    e.title or "",
                    e.url,
                    e.output_path or "",
                    e.error_message or "",
                ]
            )
        destination.write_text(buffer.getvalue(), encoding="utf-8", newline="")
        return destination
