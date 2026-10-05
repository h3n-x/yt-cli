"""Tests de componente de `YtDlpDownloader.download()` / `download_collection()`.

Se sustituye `yt_dlp.YoutubeDL` por un doble que reproduce el contrato que
usamos de yt-dlp (opciones recibidas, `progress_hooks`, `logger.error` para
entradas fallidas, `entries` con `None` para las que no se pudieron procesar),
sin acceso a red. Cubren el fallo real reportado con una playlist de YouTube
Music: un video no disponible abortaba toda la descarga.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yt_dlp.utils

from yt_cli.core import downloader as downloader_module
from yt_cli.core.downloader import YtDlpDownloader
from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import DownloadStatus, MediaType, Scope
from yt_cli.models.results import ProgressEvent

PLAYLIST_URL = "https://music.youtube.com/playlist?list=PLJnszpL2Ww1pprYTSmZANQgJErUcCY59T"
VIDEO_URL = "https://www.youtube.com/watch?v=abc123"


class FakeYoutubeDL:
    """Doble de `yt_dlp.YoutubeDL` controlado por `behaviour(fake, url)`."""

    instances: list[FakeYoutubeDL] = []

    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params
        FakeYoutubeDL.instances.append(self)

    def __enter__(self) -> FakeYoutubeDL:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    behaviour: Callable[[FakeYoutubeDL, str], dict[str, Any] | None] = staticmethod(
        lambda fake, url: None
    )

    def extract_info(self, url: str, download: bool = True) -> dict[str, Any] | None:
        return type(self).behaviour(self, url)

    def sanitize_info(self, info: dict[str, Any]) -> dict[str, Any]:
        return info

    # utilidades para los escenarios
    def hook(self, data: dict[str, Any]) -> None:
        for hook in self.params.get("progress_hooks", []):
            hook(data)

    def log_error(self, message: str) -> None:
        self.params["logger"].error(message)
        if not self.params.get("ignoreerrors"):
            raise yt_dlp.utils.DownloadError(message)


@pytest.fixture
def fake_ydl(monkeypatch: pytest.MonkeyPatch) -> type[FakeYoutubeDL]:
    FakeYoutubeDL.instances = []
    monkeypatch.setattr(downloader_module.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    return FakeYoutubeDL


def _request(tmp_path: Path, url: str, *, media: MediaType, scope: Scope) -> DownloadRequest:
    return DownloadRequest(
        url=url,
        media=media,
        scope=scope,
        output_directory=tmp_path,
        filename_template="{title}.{ext}",
    )


def _entry(video_id: str, title: str, tmp_path: Path) -> dict[str, Any]:
    return {
        "id": video_id,
        "title": title,
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "requested_downloads": [{"filepath": str(tmp_path / f"{title}.mp3")}],
    }


class TestPlaylistWithUnavailableVideo:
    """Regresión del fallo reportado: `yt-cli audio <playlist de YouTube Music>`."""

    def _playlist_behaviour(self, tmp_path: Path) -> Callable[[FakeYoutubeDL, str], dict[str, Any]]:
        def behaviour(fake: FakeYoutubeDL, url: str) -> dict[str, Any]:
            entries: list[dict[str, Any] | None] = [_entry("aaa", "Tema 1", tmp_path)]
            # yt-dlp colorea el prefijo ERROR: si stderr es una TTY
            fake.log_error("\x1b[0;31mERROR:\x1b[0m [youtube] eRGbT2uxj4g: Video unavailable")
            entries.append(None)
            entries.append(_entry("ccc", "Tema 3", tmp_path))
            return {"title": "Mi playlist", "entries": entries}

        return behaviour

    def test_unavailable_entry_does_not_abort_the_rest(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        fake_ydl.behaviour = staticmethod(self._playlist_behaviour(tmp_path))
        request = _request(tmp_path, PLAYLIST_URL, media=MediaType.AUDIO, scope=Scope.PLAYLIST)

        result = YtDlpDownloader().download(request)

        assert fake_ydl.instances[0].params["ignoreerrors"] is True
        assert result.status is DownloadStatus.PARTIAL
        assert result.entry_count == 3
        assert result.entry_failures == 1
        assert [e.status for e in result.entries] == [
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
            DownloadStatus.COMPLETED,
        ]

    def test_failed_entry_gets_clean_message_id_and_hint(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        fake_ydl.behaviour = staticmethod(self._playlist_behaviour(tmp_path))
        request = _request(tmp_path, PLAYLIST_URL, media=MediaType.AUDIO, scope=Scope.PLAYLIST)

        failed = YtDlpDownloader().download(request).entries[1]

        assert failed.url == "https://www.youtube.com/watch?v=eRGbT2uxj4g"
        assert failed.error_message is not None
        assert failed.error_message.startswith("eRGbT2uxj4g: Video unavailable")
        assert "\x1b" not in failed.error_message
        assert "región" in failed.error_message  # pista accionable

    def test_audio_collection_uses_audio_postprocessor(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        fake_ydl.behaviour = staticmethod(self._playlist_behaviour(tmp_path))
        request = _request(tmp_path, PLAYLIST_URL, media=MediaType.AUDIO, scope=Scope.PLAYLIST)

        YtDlpDownloader().download(request)

        params = fake_ydl.instances[0].params
        assert params["format"] == "bestaudio/best"
        assert params["noplaylist"] is False
        assert any(pp["key"] == "FFmpegExtractAudio" for pp in params["postprocessors"])


class TestArchiveSkips:
    def test_entry_already_in_archive_is_skipped_not_failed(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        def behaviour(fake: FakeYoutubeDL, url: str) -> dict[str, Any]:
            fake.params["logger"].debug(
                "[download] aaa: Tema 1 has already been recorded in the archive"
            )
            return {"title": "P", "entries": [None, _entry("bbb", "Tema 2", tmp_path)]}

        fake_ydl.behaviour = staticmethod(behaviour)
        request = _request(tmp_path, PLAYLIST_URL, media=MediaType.AUDIO, scope=Scope.PLAYLIST)

        result = YtDlpDownloader().download(request)

        assert result.status is DownloadStatus.COMPLETED
        assert result.entries[0].status is DownloadStatus.SKIPPED
        assert result.entry_failures == 0


class TestSingleDownload:
    def test_success_reports_final_path_and_title(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        def behaviour(fake: FakeYoutubeDL, url: str) -> dict[str, Any]:
            fake.hook({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10})
            return _entry("abc123", "Video", tmp_path)

        fake_ydl.behaviour = staticmethod(behaviour)
        events: list[ProgressEvent] = []
        request = _request(tmp_path, VIDEO_URL, media=MediaType.VIDEO, scope=Scope.SINGLE)

        result = YtDlpDownloader().download(request, progress_callback=events.append)

        assert result.status is DownloadStatus.COMPLETED
        assert result.title == "Video"
        assert result.output_path == tmp_path / "Video.mp3"
        assert events[0].percent == 50.0
        assert fake_ydl.instances[0].params["ignoreerrors"] is False

    def test_yt_dlp_error_becomes_failed_result_with_clean_message(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        def behaviour(fake: FakeYoutubeDL, url: str) -> dict[str, Any]:
            fake.log_error(
                "ERROR: [youtube] abc123: Private video. Sign in if you've been granted access"
            )
            raise AssertionError("no se alcanza")

        fake_ydl.behaviour = staticmethod(behaviour)
        request = _request(tmp_path, VIDEO_URL, media=MediaType.VIDEO, scope=Scope.SINGLE)

        result = YtDlpDownloader().download(request)

        assert result.status is DownloadStatus.FAILED
        assert result.error_message is not None
        assert result.error_message.startswith("abc123: Private video")
        assert "[youtube]" not in result.error_message

    def test_error_text_with_markup_like_brackets_does_not_crash(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        """Antes, un mensaje con '[/x]' lanzaba MarkupError desde el logging."""

        def behaviour(fake: FakeYoutubeDL, url: str) -> dict[str, Any]:
            fake.log_error("ERROR: [youtube] abc123: título [/bold] raro")
            raise AssertionError("no se alcanza")

        fake_ydl.behaviour = staticmethod(behaviour)
        request = _request(tmp_path, VIDEO_URL, media=MediaType.VIDEO, scope=Scope.SINGLE)

        result = YtDlpDownloader().download(request)
        assert result.error_message is not None
        assert "[/bold]" in result.error_message

    def test_info_none_is_failed(self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]) -> None:
        fake_ydl.behaviour = staticmethod(lambda fake, url: None)
        request = _request(tmp_path, VIDEO_URL, media=MediaType.VIDEO, scope=Scope.SINGLE)
        assert YtDlpDownloader().download(request).status is DownloadStatus.FAILED

    def test_os_error_becomes_failed_result(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        def behaviour(fake: FakeYoutubeDL, url: str) -> dict[str, Any]:
            raise OSError(28, "No space left on device")

        fake_ydl.behaviour = staticmethod(behaviour)
        request = _request(tmp_path, VIDEO_URL, media=MediaType.VIDEO, scope=Scope.SINGLE)

        result = YtDlpDownloader().download(request)
        assert result.status is DownloadStatus.FAILED
        assert "No space left" in (result.error_message or "")


class TestCancellation:
    def test_cancel_stops_download_at_next_progress_event(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        downloader = YtDlpDownloader()

        def behaviour(fake: FakeYoutubeDL, url: str) -> dict[str, Any]:
            downloader.cancel()
            fake.hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 10})
            raise AssertionError("el hook debería haber cancelado")

        fake_ydl.behaviour = staticmethod(behaviour)
        request = _request(tmp_path, VIDEO_URL, media=MediaType.VIDEO, scope=Scope.SINGLE)

        assert downloader.download(request).status is DownloadStatus.CANCELLED

    def test_cancelled_downloader_does_not_start_new_downloads(
        self, tmp_path: Path, fake_ydl: type[FakeYoutubeDL]
    ) -> None:
        downloader = YtDlpDownloader()
        downloader.cancel()
        request = _request(tmp_path, VIDEO_URL, media=MediaType.VIDEO, scope=Scope.SINGLE)

        assert downloader.download(request).status is DownloadStatus.CANCELLED
        assert fake_ydl.instances == []


class TestMetadataExtraction:
    def test_wraps_yt_dlp_errors_in_own_download_error(self, fake_ydl: type[FakeYoutubeDL]) -> None:
        def behaviour(fake: FakeYoutubeDL, url: str) -> dict[str, Any]:
            raise yt_dlp.utils.DownloadError("ERROR: [youtube] x: Video unavailable")

        fake_ydl.behaviour = staticmethod(behaviour)
        with pytest.raises(downloader_module.DownloadError, match="Video unavailable"):
            YtDlpDownloader().extract_metadata_only(VIDEO_URL)

    def test_respects_proxy_and_cookies(self, fake_ydl: type[FakeYoutubeDL]) -> None:
        fake_ydl.behaviour = staticmethod(lambda fake, url: {"entries": []})
        YtDlpDownloader(
            proxy="http://p:3128", cookies_from_browser="firefox:perfil"
        ).extract_metadata_only("ytsearch1:x", flat=True)
        params = fake_ydl.instances[0].params
        assert params["proxy"] == "http://p:3128"
        assert params["cookiesfrombrowser"] == ("firefox", "perfil", None, None)
        assert params["extract_flat"] == "in_playlist"
