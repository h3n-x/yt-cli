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
from pydantic import BaseModel, Field

from yt_cli.models.enums import DownloadKind, DownloadStatus
from yt_cli.utils.locking import exclusive_lock


class HistoryEntry(BaseModel):
    url: str
    title: str | None
    kind: DownloadKind
    status: DownloadStatus
    output_path: str | None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_message: str | None = None


def history_file_path() -> Path:
    return Path(user_data_dir("yt-cli", appauthor=False)) / "history.json"


class HistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or history_file_path()

    def _read_all(self) -> list[HistoryEntry]:
        if not self._path.exists():
            return []
        raw = orjson.loads(self._path.read_bytes())
        return [HistoryEntry.model_validate(item) for item in raw]

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
        # El lock envuelve TODO el ciclo lectura-modificación-escritura, no solo
        # la escritura: dos procesos que llamen a add() casi simultáneamente
        # deben serializarse antes de leer, o el segundo pisaría el append del
        # primero (corrige B7 de AUDIT_REPORT.md).
        with exclusive_lock(self._path):
            entries = self._read_all()
            entries.append(entry)
            self._write_all(entries)

    def list_recent(self, limit: int = 50) -> list[HistoryEntry]:
        entries = self.list_all()
        return entries[:limit]

    def list_all(self) -> list[HistoryEntry]:
        """Todas las entradas, ordenadas de la más reciente a la más antigua."""
        return sorted(self._read_all(), key=lambda e: e.timestamp, reverse=True)

    def find_by_url(self, url: str) -> HistoryEntry | None:
        for entry in reversed(self._read_all()):
            if entry.url == url and entry.status is DownloadStatus.COMPLETED:
                return entry
        return None

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
        writer.writerow(["timestamp", "kind", "status", "title", "url", "output_path", "error_message"])
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
