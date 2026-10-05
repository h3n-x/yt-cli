"""Cache de resultados de yt-dlp con TTL (hoy: resultados de `yt-cli search`,
para no repetir la misma consulta a YouTube dentro de la ventana configurada
en `general.cache_ttl_hours`; se desactiva con `general.cache_enabled = false`).

Almacenamiento: un archivo JSON por entrada bajo
~/.cache/yt-cli/metadata/<sha256(url)>.json, para poder invalidar entradas
individuales sin parsear un archivo monolítico.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import orjson
from platformdirs import user_cache_dir

from yt_cli.utils.locking import exclusive_lock


def cache_dir() -> Path:
    return Path(user_cache_dir("yt-cli", appauthor=False)) / "metadata"


@dataclass(slots=True)
class CacheStats:
    entry_count: int
    total_bytes: int


class MetadataCache:
    def __init__(self, ttl_hours: int, base_dir: Path | None = None) -> None:
        self._ttl = timedelta(hours=ttl_hours)
        self._dir = base_dir or cache_dir()

    def _key_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.json"

    def get(self, url: str) -> dict[str, Any] | None:
        if self._ttl.total_seconds() <= 0:
            return None  # cache deshabilitado

        path = self._key_path(url)
        if not path.exists():
            return None

        try:
            payload = orjson.loads(path.read_bytes())
            cached_at = datetime.fromisoformat(payload["cached_at"])
        except (orjson.JSONDecodeError, KeyError, TypeError, ValueError):
            path.unlink(missing_ok=True)  # entrada corrupta: se descarta
            return None
        if datetime.now(UTC) - cached_at > self._ttl:
            path.unlink(missing_ok=True)
            return None

        return cast(dict[str, Any], payload["data"])

    def set(self, url: str, data: dict[str, Any]) -> None:
        if self._ttl.total_seconds() <= 0:
            return

        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {"cached_at": datetime.now(UTC).isoformat(), "data": data}
        path = self._key_path(url)
        with exclusive_lock(path):
            tmp_path = path.with_suffix(".json.tmp")
            tmp_path.write_bytes(orjson.dumps(payload))
            tmp_path.replace(path)

    def clear(self) -> int:
        if not self._dir.exists():
            return 0
        count = 0
        for entry in self._dir.glob("*.json"):
            entry.unlink()
            count += 1
        return count

    def stats(self) -> CacheStats:
        if not self._dir.exists():
            return CacheStats(entry_count=0, total_bytes=0)
        files = list(self._dir.glob("*.json"))
        return CacheStats(
            entry_count=len(files),
            total_bytes=sum(f.stat().st_size for f in files),
        )
