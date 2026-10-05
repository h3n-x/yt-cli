from pathlib import Path

import pytest

from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import DownloadKind, DownloadStatus, MediaType, Scope
from yt_cli.models.results import DownloadResult, EntryResult
from yt_cli.services.history import HistoryEntry, HistoryError, HistoryStore


def _entry(
    url: str = "https://youtu.be/abc", status: DownloadStatus = DownloadStatus.COMPLETED
) -> HistoryEntry:
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

    def test_add_many_writes_all_rows_at_once(self, tmp_path: Path) -> None:
        store = HistoryStore(path=tmp_path / "history.json")
        store.add_many([_entry(url=f"https://youtu.be/{i}") for i in range(3)])
        assert len(store.list_all()) == 3

    def test_add_many_with_empty_list_does_not_create_file(self, tmp_path: Path) -> None:
        path = tmp_path / "history.json"
        HistoryStore(path=path).add_many([])
        assert not path.exists()

    def test_corrupt_file_raises_history_error(self, tmp_path: Path) -> None:
        path = tmp_path / "history.json"
        path.write_text("{no es json")
        with pytest.raises(HistoryError, match="dañado"):
            HistoryStore(path=path).list_all()

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

        assert rows[0] == [
            "timestamp",
            "kind",
            "status",
            "title",
            "url",
            "output_path",
            "error_message",
        ]
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


class TestRowsForResult:
    def _playlist_result(self, tmp_path: Path) -> DownloadResult:
        request = DownloadRequest(
            url="https://music.youtube.com/playlist?list=PLx",
            media=MediaType.AUDIO,
            scope=Scope.PLAYLIST,
            output_directory=tmp_path,
            filename_template="{title}.{ext}",
        )
        return DownloadResult(
            request=request,
            status=DownloadStatus.PARTIAL,
            output_path=tmp_path,
            title="Mi playlist",
            entries=[
                EntryResult(
                    status=DownloadStatus.COMPLETED,
                    title="Tema 1",
                    url="https://www.youtube.com/watch?v=aaa",
                    output_path=tmp_path / "Tema 1.mp3",
                ),
                EntryResult(
                    status=DownloadStatus.FAILED,
                    title=None,
                    url="https://www.youtube.com/watch?v=bbb",
                    output_path=None,
                    error_message="bbb: Video unavailable",
                ),
            ],
        )

    def test_collection_produces_one_row_per_video_with_video_url(self, tmp_path: Path) -> None:
        rows = HistoryEntry.rows_for(self._playlist_result(tmp_path))
        assert [r.url for r in rows] == [
            "https://www.youtube.com/watch?v=aaa",
            "https://www.youtube.com/watch?v=bbb",
        ]
        assert all(r.kind is DownloadKind.AUDIO for r in rows)
        assert rows[1].error_message == "bbb: Video unavailable"

    def test_single_download_produces_one_row(self, tmp_path: Path) -> None:
        request = DownloadRequest(
            url="https://youtu.be/abc",
            media=MediaType.VIDEO,
            output_directory=tmp_path,
            filename_template="{title}.{ext}",
        )
        result = DownloadResult(
            request=request,
            status=DownloadStatus.COMPLETED,
            output_path=tmp_path / "x.mp4",
            title="X",
        )
        rows = HistoryEntry.rows_for(result)
        assert len(rows) == 1
        assert rows[0].kind is DownloadKind.VIDEO
