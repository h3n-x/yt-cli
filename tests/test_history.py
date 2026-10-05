from pathlib import Path

from yt_cli.models.enums import DownloadKind, DownloadStatus
from yt_cli.services.history import HistoryEntry, HistoryStore


def _entry(url: str = "https://youtu.be/abc", status: DownloadStatus = DownloadStatus.COMPLETED) -> HistoryEntry:
    return HistoryEntry(
        url=url,
        title="Video de prueba",
        kind=DownloadKind.VIDEO,
        status=status,
        output_path="/tmp/video.mp4",
    )


class TestHistoryStore:
    def test_starts_empty(self, tmp_path: Path) -> None:
        store = HistoryStore(path=tmp_path / "history.json")
        assert store.list_recent() == []

    def test_add_and_list(self, tmp_path: Path) -> None:
        store = HistoryStore(path=tmp_path / "history.json")
        store.add(_entry())
        entries = store.list_recent()
        assert len(entries) == 1
        assert entries[0].url == "https://youtu.be/abc"

    def test_list_recent_respects_limit(self, tmp_path: Path) -> None:
        store = HistoryStore(path=tmp_path / "history.json")
        for i in range(5):
            store.add(_entry(url=f"https://youtu.be/{i}"))
        assert len(store.list_recent(limit=2)) == 2

    def test_find_by_url_only_returns_completed(self, tmp_path: Path) -> None:
        store = HistoryStore(path=tmp_path / "history.json")
        store.add(_entry(url="https://youtu.be/failed", status=DownloadStatus.FAILED))
        assert store.find_by_url("https://youtu.be/failed") is None

        store.add(_entry(url="https://youtu.be/ok", status=DownloadStatus.COMPLETED))
        found = store.find_by_url("https://youtu.be/ok")
        assert found is not None
        assert found.status is DownloadStatus.COMPLETED

    def test_clear_empties_history(self, tmp_path: Path) -> None:
        store = HistoryStore(path=tmp_path / "history.json")
        store.add(_entry())
        store.clear()
        assert store.list_recent() == []

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "history.json"
        HistoryStore(path=path).add(_entry())
        reopened = HistoryStore(path=path)
        assert len(reopened.list_recent()) == 1


class TestHistoryExport:
    def test_export_json_produces_valid_array(self, tmp_path: Path) -> None:
        import orjson

        store = HistoryStore(path=tmp_path / "history.json")
        store.add(_entry(url="https://youtu.be/a"))
        store.add(_entry(url="https://youtu.be/b"))

        destination = tmp_path / "export.json"
        store.export_json(destination)

        data = orjson.loads(destination.read_bytes())
        assert len(data) == 2
        assert {d["url"] for d in data} == {"https://youtu.be/a", "https://youtu.be/b"}

    def test_export_csv_has_header_and_rows(self, tmp_path: Path) -> None:
        import csv

        store = HistoryStore(path=tmp_path / "history.json")
        store.add(_entry(url="https://youtu.be/a"))

        destination = tmp_path / "export.csv"
        store.export_csv(destination)

        with destination.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        assert rows[0] == ["timestamp", "kind", "status", "title", "url", "output_path", "error_message"]
        assert len(rows) == 2
        assert rows[1][4] == "https://youtu.be/a"

    def test_export_on_empty_history_produces_header_only_csv(self, tmp_path: Path) -> None:
        import csv

        store = HistoryStore(path=tmp_path / "history.json")
        destination = tmp_path / "export.csv"
        store.export_csv(destination)

        with destination.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 1  # solo el header
