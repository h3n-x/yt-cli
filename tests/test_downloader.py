"""Tests de yt_cli.core.downloader.

NOTA HONESTA (ver TEST_REPORT.md): este módulo importa `yt_dlp`, que no está
instalado en el sandbox de esta sesión (sin red para `pip install`). Estos
tests están escritos y revisados manualmente por lógica, pero no se
ejecutaron en esta sesión; se ejecutarán en CI, donde `yt-dlp` sí está
disponible como dependencia declarada del proyecto.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from yt_cli.core.downloader import (
    _RETRY_SLEEP_FUNCTIONS,
    DownloadError,
    YtDlpDownloader,
    _map_yt_dlp_progress,
)
from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import DownloadKind, DownloadStatus, OverwritePolicy


def _request(
    tmp_path: Path,
    *,
    kind: DownloadKind = DownloadKind.VIDEO,
    overwrite_policy: OverwritePolicy = OverwritePolicy.SKIP,
    template: str = "{title}.{ext}",
) -> DownloadRequest:
    return DownloadRequest(
        url="https://www.youtube.com/watch?v=abc123",
        kind=kind,
        output_directory=tmp_path,
        filename_template=template,
        overwrite_policy=overwrite_policy,
    )


class TestRetryBackoff:
    """Corrige la ausencia de reintentos inteligentes (phase_8, prioridad #3)."""

    @pytest.mark.parametrize(
        ("kind", "ceiling"), [("http", 60), ("fragment", 30), ("file_access", 10)]
    )
    def test_backoff_is_bounded(self, kind: str, ceiling: int) -> None:
        func = _RETRY_SLEEP_FUNCTIONS[kind]
        assert all(func(n) <= ceiling for n in range(20))

    def test_backoff_grows_until_ceiling(self) -> None:
        func = _RETRY_SLEEP_FUNCTIONS["http"]
        values = [func(n) for n in range(6)]
        assert values == sorted(values)
        assert values[-1] == 60


class TestMapProgress:
    def test_percent_computed_from_bytes(self) -> None:
        event = _map_yt_dlp_progress(
            {"status": "downloading", "downloaded_bytes": 25, "total_bytes": 100}
        )
        assert event.percent == 25.0

    def test_missing_total_bytes_has_no_percent(self) -> None:
        event = _map_yt_dlp_progress({"status": "downloading", "downloaded_bytes": 25})
        assert event.percent is None

    def test_unknown_status_defaults_to_downloading(self) -> None:
        event = _map_yt_dlp_progress({"status": "some_future_yt_dlp_status"})
        assert event.status is DownloadStatus.DOWNLOADING


class TestBuildYdlOpts:
    """Corrige B1 (clave muerta) y B3 (rate limit no conectado)."""

    def test_rate_limit_converted_to_bytes_per_second(self, tmp_path: Path) -> None:
        downloader = YtDlpDownloader(rate_limit_kbps=500)
        opts = downloader._build_ydl_opts(_request(tmp_path), None)
        assert opts["ratelimit"] == 500 * 1024

    def test_no_rate_limit_key_when_unset(self, tmp_path: Path) -> None:
        downloader = YtDlpDownloader()
        opts = downloader._build_ydl_opts(_request(tmp_path), None)
        assert "ratelimit" not in opts

    def test_retry_sleep_functions_are_wired(self, tmp_path: Path) -> None:
        downloader = YtDlpDownloader()
        opts = downloader._build_ydl_opts(_request(tmp_path), None)
        assert opts["retry_sleep_functions"] is _RETRY_SLEEP_FUNCTIONS

    def test_no_dead_nooverwrites_key(self, tmp_path: Path) -> None:
        """B1: la clave 'nooverwrites' no existe en yt_dlp.YoutubeDL; se retiró."""
        downloader = YtDlpDownloader()
        opts = downloader._build_ydl_opts(
            _request(tmp_path, overwrite_policy=OverwritePolicy.SKIP), None
        )
        assert "nooverwrites" not in opts
        assert opts["overwrites"] is False


class TestRenameConflictResolution:
    """Corrige B2: overwrite_policy=RENAME estaba definido pero no implementado."""

    def test_returns_none_when_metadata_extraction_fails(self, tmp_path: Path) -> None:
        downloader = YtDlpDownloader()
        downloader.extract_metadata_only = MagicMock(side_effect=DownloadError("boom"))  # type: ignore[method-assign]
        request = _request(tmp_path, overwrite_policy=OverwritePolicy.RENAME)
        assert downloader._resolve_rename_target(request) is None

    def test_returns_original_path_when_no_conflict(self, tmp_path: Path) -> None:
        downloader = YtDlpDownloader()
        downloader.extract_metadata_only = MagicMock(  # type: ignore[method-assign]
            return_value={"title": "Mi Video", "ext": "mp4"}
        )
        request = _request(tmp_path, overwrite_policy=OverwritePolicy.RENAME)
        assert downloader._resolve_rename_target(request) == str(tmp_path / "Mi Video.mp4")

    def test_adds_numeric_suffix_on_single_conflict(self, tmp_path: Path) -> None:
        (tmp_path / "Mi Video.mp4").write_text("existente")
        downloader = YtDlpDownloader()
        downloader.extract_metadata_only = MagicMock(  # type: ignore[method-assign]
            return_value={"title": "Mi Video", "ext": "mp4"}
        )
        request = _request(tmp_path, overwrite_policy=OverwritePolicy.RENAME)
        assert downloader._resolve_rename_target(request) == str(tmp_path / "Mi Video (1).mp4")

    def test_increments_past_multiple_conflicts(self, tmp_path: Path) -> None:
        (tmp_path / "Mi Video.mp4").write_text("existente")
        (tmp_path / "Mi Video (1).mp4").write_text("existente")
        downloader = YtDlpDownloader()
        downloader.extract_metadata_only = MagicMock(  # type: ignore[method-assign]
            return_value={"title": "Mi Video", "ext": "mp4"}
        )
        request = _request(tmp_path, overwrite_policy=OverwritePolicy.RENAME)
        assert downloader._resolve_rename_target(request) == str(tmp_path / "Mi Video (2).mp4")


class TestCollectionSummary:
    """Corrige B4: playlists/canales siempre reportaban COMPLETED aunque
    hubieran fallado entradas individuales.
    """

    def test_all_entries_succeed_reports_completed(self, tmp_path: Path) -> None:
        downloader = YtDlpDownloader()
        request = _request(tmp_path, kind=DownloadKind.PLAYLIST)
        info = {
            "entries": [
                {"title": "A", "requested_downloads": [{"filepath": "/tmp/a.mp4"}]},
                {"title": "B", "requested_downloads": [{"filepath": "/tmp/b.mp4"}]},
            ]
        }
        result = downloader._summarize_collection_result(request, info)
        assert result.status is DownloadStatus.COMPLETED
        assert result.entry_count == 2
        assert result.entry_failures == 0

    def test_mixed_results_report_partial(self, tmp_path: Path) -> None:
        downloader = YtDlpDownloader()
        request = _request(tmp_path, kind=DownloadKind.PLAYLIST)
        info = {
            "entries": [
                {"title": "A", "requested_downloads": [{"filepath": "/tmp/a.mp4"}]},
                None,  # entrada que yt-dlp no pudo extraer (video privado/eliminado)
            ]
        }
        result = downloader._summarize_collection_result(request, info)
        assert result.status is DownloadStatus.PARTIAL
        assert result.entry_failures == 1
        assert result.entry_count == 2

    def test_all_entries_fail_reports_failed(self, tmp_path: Path) -> None:
        downloader = YtDlpDownloader()
        request = _request(tmp_path, kind=DownloadKind.CHANNEL)
        info = {"entries": [None, None]}
        result = downloader._summarize_collection_result(request, info)
        assert result.status is DownloadStatus.FAILED

    def test_single_resolved_video_without_entries_key(self, tmp_path: Path) -> None:
        """Un canal/playlist que resuelve a un único video no trae 'entries'."""
        downloader = YtDlpDownloader()
        request = _request(tmp_path, kind=DownloadKind.CHANNEL)
        info = {"title": "Solo", "requested_downloads": [{"filepath": "/tmp/solo.mp4"}]}
        result = downloader._summarize_collection_result(request, info)
        assert result.status is DownloadStatus.COMPLETED
        assert result.entry_count == 1

    def test_iter_entry_results_maps_each_entry_independently(self, tmp_path: Path) -> None:
        downloader = YtDlpDownloader()
        request = _request(tmp_path, kind=DownloadKind.PLAYLIST)
        info = {
            "entries": [
                {"title": "A", "requested_downloads": [{"filepath": "/tmp/a.mp4"}]},
                None,
            ]
        }
        results = downloader.iter_collection_entry_results(request, info)
        assert len(results) == 2
        assert results[0].status is DownloadStatus.COMPLETED
        assert results[0].title == "A"
        assert results[1].status is DownloadStatus.FAILED
