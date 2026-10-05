"""Regresiones de los hallazgos de docs/AUDIT_2026-10.md.

Cada clase referencia el identificador del hallazgo (Q1, H1, A2, ...).
"""

from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path

import pytest
from rich.console import Console

from yt_cli.core import dependencies
from yt_cli.core.downloader import (
    PROTECTED_YTDLP_OPTIONS,
    YtDlpDownloader,
    build_output_template,
    build_postprocessors,
)
from yt_cli.core.errors import clean_message, explain
from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import (
    AudioFormat,
    DownloadKind,
    DownloadStatus,
    MediaType,
    Scope,
    VideoFormat,
)
from yt_cli.models.results import DownloadResult, ProgressEvent
from yt_cli.services.queue import DownloadQueue
from yt_cli.utils.logging import configure_logging
from yt_cli.utils.naming import render_filename_template
from yt_cli.utils.progress_ui import RichDownloadProgress
from yt_cli.utils.theme import YT_CLI_THEME
from yt_cli.utils.validators import InvalidURLError, detect_scope, validate_url


def _request(tmp_path: Path, **overrides: object) -> DownloadRequest:
    data: dict[str, object] = {
        "url": "https://www.youtube.com/watch?v=abc123",
        "output_directory": tmp_path,
        "filename_template": "{title}.{ext}",
    }
    data.update(overrides)
    return DownloadRequest.model_validate(data)


class TestScopeDetection:
    """Q2/A1: la URL determina si es una colección, sin importar el comando."""

    @pytest.mark.parametrize(
        ("url", "scope"),
        [
            ("https://music.youtube.com/playlist?list=PLJnszpL2Ww1&si=8pQN", Scope.PLAYLIST),
            ("https://www.youtube.com/playlist?list=PLx", Scope.PLAYLIST),
            ("https://music.youtube.com/browse/MPREb_abc", Scope.PLAYLIST),
            ("https://www.youtube.com/watch?v=abc&list=PLx", Scope.SINGLE),
            ("https://youtu.be/abc?si=x", Scope.SINGLE),
            ("https://www.youtube.com/@canal", Scope.CHANNEL),
            ("https://www.youtube.com/@canal/videos", Scope.CHANNEL),
            ("https://www.youtube.com/channel/UCabc", Scope.CHANNEL),
        ],
    )
    def test_detect_scope(self, url: str, scope: Scope) -> None:
        assert detect_scope(url) is scope

    def test_legacy_kind_is_still_accepted(self, tmp_path: Path) -> None:
        request = _request(tmp_path, kind=DownloadKind.PLAYLIST)
        assert request.scope is Scope.PLAYLIST
        assert request.media is MediaType.VIDEO
        assert request.kind is DownloadKind.PLAYLIST

    def test_audio_playlist_kind_label(self, tmp_path: Path) -> None:
        request = _request(tmp_path, media=MediaType.AUDIO, scope=Scope.PLAYLIST)
        assert request.kind is DownloadKind.PLAYLIST
        assert request.target_extension == "mp3"


class TestUrlValidationUsesHostname:
    """M4: se compara `hostname`, no `netloc`."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com:443/watch?v=x",
            "https://user@youtube.com/watch?v=x",
            "https://www.youtube-nocookie.com/embed/x",
            "https://MUSIC.YouTube.com/playlist?list=x",
        ],
    )
    def test_accepts(self, url: str) -> None:
        assert validate_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "https://youtube.com@evil.example/watch?v=x",
            "https://evil.example/?u=youtube.com",
            "https://notyoutube.com/watch?v=x",
            "https://youtube.com:abc/watch",
        ],
    )
    def test_rejects(self, url: str) -> None:
        with pytest.raises(InvalidURLError):
            validate_url(url)


class TestErrorTranslation:
    """H1/X7: mensajes limpios (sin ANSI ni prefijos) y con pista."""

    def test_strips_ansi_and_prefix(self) -> None:
        raw = "\x1b[1m\x1b[0;31mERROR:\x1b[1m\x1b[0m [youtube] eRGbT2uxj4g: Video unavailable"
        assert clean_message(raw) == "[youtube] eRGbT2uxj4g: Video unavailable"

    def test_extracts_video_id_and_hint(self) -> None:
        explained = explain("ERROR: [youtube] eRGbT2uxj4g: Video unavailable")
        assert explained.video_id == "eRGbT2uxj4g"
        assert explained.message == "eRGbT2uxj4g: Video unavailable"
        assert explained.hint is not None
        assert "región" in str(explained)

    def test_bot_check_suggests_cookies(self) -> None:
        explained = explain("ERROR: [youtube] x: Sign in to confirm you're not a bot")
        assert "cookies_from_browser" in str(explained)

    def test_unknown_error_has_no_hint(self) -> None:
        assert explain("algo raro").hint is None


class TestFilenameTemplates:
    """A2: un '/' en los metadatos ya no crea subdirectorios."""

    def test_slash_in_metadata_is_not_a_directory(self) -> None:
        rendered = render_filename_template(
            "{uploader}/{title}.{ext}", {"uploader": "Ch/an", "title": "AC/DC: Live", "ext": "mp3"}
        )
        assert rendered.count("/") == 1
        assert rendered.startswith("Ch_an/")

    @pytest.mark.parametrize("template", ["{title.__class__}", "{title!r}", "{title:>10}", "{0}"])
    def test_rejects_non_simple_placeholders(self, template: str) -> None:
        with pytest.raises(ValueError, match="no soportado"):
            render_filename_template(template, {})

    def test_literal_percent_is_escaped_for_yt_dlp(self, tmp_path: Path) -> None:
        request = _request(tmp_path, filename_template="100% {title}.{ext}")
        assert build_output_template(request).endswith("/100%% %(title)s.%(ext)s")


class TestPostprocessors:
    """H2: no se pide una carátula que yt-dlp no puede incrustar."""

    def _keys(self, request: DownloadRequest) -> list[str]:
        return [pp["key"] for pp in build_postprocessors(request)]

    @pytest.mark.parametrize("fmt", [AudioFormat.WAV, AudioFormat.AAC])
    def test_no_thumbnail_for_unsupported_audio_containers(
        self, tmp_path: Path, fmt: AudioFormat
    ) -> None:
        request = _request(tmp_path, media=MediaType.AUDIO, audio_format=fmt)
        assert "EmbedThumbnail" not in self._keys(request)

    def test_no_thumbnail_for_webm_video(self, tmp_path: Path) -> None:
        request = _request(tmp_path, video_format=VideoFormat.WEBM)
        assert "EmbedThumbnail" not in self._keys(request)

    def test_opus_thumbnail_depends_on_mutagen(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        request = _request(tmp_path, media=MediaType.AUDIO, audio_format=AudioFormat.OPUS)
        monkeypatch.setattr("yt_cli.core.downloader.has_mutagen", lambda: False)
        assert "EmbedThumbnail" not in self._keys(request)
        monkeypatch.setattr("yt_cli.core.downloader.has_mutagen", lambda: True)
        assert "EmbedThumbnail" in self._keys(request)

    def test_sponsorblock_runs_before_metadata(self, tmp_path: Path) -> None:
        request = _request(tmp_path, sponsorblock_remove=["sponsor"])
        keys = self._keys(request)
        assert (
            keys.index("SponsorBlock") < keys.index("ModifyChapters") < keys.index("FFmpegMetadata")
        )


class TestYtDlpOptions:
    def test_colors_disabled(self, tmp_path: Path) -> None:
        """H1: sin esto, yt-dlp mandaba códigos ANSI al logger."""
        opts = YtDlpDownloader()._build_ydl_opts(_request(tmp_path), None)
        assert opts["color"] == {"stdout": "never", "stderr": "never"}

    def test_extra_options_cannot_override_protected_keys(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        downloader = YtDlpDownloader(
            extra_options={"geo_bypass_country": "ES", "outtmpl": "/tmp/x", "logger": None}
        )
        with caplog.at_level(logging.WARNING):
            opts = downloader._build_ydl_opts(_request(tmp_path), None)
        assert opts["geo_bypass_country"] == "ES"
        assert opts["outtmpl"] != "/tmp/x"
        assert opts["logger"] is not None
        assert "outtmpl" in PROTECTED_YTDLP_OPTIONS

    def test_playlist_items_and_archive(self, tmp_path: Path) -> None:
        archive = tmp_path / "data" / "archive.txt"
        request = _request(
            tmp_path,
            scope=Scope.PLAYLIST,
            url="https://www.youtube.com/playlist?list=PLx",
            playlist_items="1:5",
            download_archive=archive,
        )
        opts = YtDlpDownloader()._build_ydl_opts(request, None)
        assert opts["playlist_items"] == "1:5"
        assert opts["download_archive"] == str(archive)
        assert archive.parent.is_dir()

    @pytest.mark.parametrize("items", ["1;rm -rf", "abc", ""])
    def test_invalid_playlist_items_rejected(self, tmp_path: Path, items: str) -> None:
        with pytest.raises(ValueError):
            _request(tmp_path, playlist_items=items)


class TestLoggingIsNotMarkup:
    """Q1: el texto externo que pasa por logging no se interpreta como markup."""

    def test_brackets_survive_and_closing_tags_do_not_crash(self) -> None:
        buffer = io.StringIO()
        configure_logging(debug=False, console=Console(file=buffer, width=200))
        log = logging.getLogger("yt_cli.test")
        log.error("ERROR: [youtube] abc: Video unavailable")
        log.error("Título [/bold] raro")
        output = buffer.getvalue()
        assert "[youtube]" in output
        assert "[/bold]" in output


class TestProgressEscapesExternalText:
    """S2: títulos y errores no pueden inyectar estilos ni romper el render."""

    # yt-dlp nunca deja un '/' en un nombre de archivo (lo cambia por '⧸'),
    # así que las etiquetas de cierre llegan como '[⧸red]'.
    @pytest.mark.parametrize(
        "title", ["[red]FAKE[⧸red].webm", "Remix [value] x.webm", "Canción [Official Video].mp3"]
    )
    def test_titles_render_literally(self, title: str) -> None:
        console = Console(file=io.StringIO(), width=300, theme=YT_CLI_THEME)
        with RichDownloadProgress(console) as ui:
            task = ui.add_task("https://youtu.be/x")
            ui.update(
                task,
                ProgressEvent(
                    status=DownloadStatus.DOWNLOADING,
                    filename=f"/m/{title}",
                    downloaded_bytes=1,
                    total_bytes=2,
                    playlist_index=3,
                    playlist_count=12,
                ),
            )
        output = console.file.getvalue()  # type: ignore[attr-defined]
        assert title in output
        assert "3/12" in output

    def test_finish_with_markup_in_error_does_not_crash(self, tmp_path: Path) -> None:
        console = Console(file=io.StringIO(), width=300, theme=YT_CLI_THEME)
        result = DownloadResult(
            request=_request(tmp_path),
            status=DownloadStatus.FAILED,
            output_path=None,
            title="algo [/error] roto",
            error_message="x [/] y",
        )
        with RichDownloadProgress(console) as ui:
            ui.finish(ui.add_task("https://youtu.be/x"), result)
        assert "algo [/error] roto" in console.file.getvalue()  # type: ignore[attr-defined]


class _FlakyDownloader:
    def __init__(self) -> None:
        self.cancelled = False

    def download(
        self, request: DownloadRequest, progress_callback: object = None
    ) -> DownloadResult:
        if request.url.endswith("boom"):
            raise RuntimeError("fallo inesperado")
        return DownloadResult(
            request=request, status=DownloadStatus.COMPLETED, output_path=None, title="ok"
        )

    def cancel(self) -> None:
        self.cancelled = True


class TestDownloadQueue:
    """H4: un fallo inesperado no tumba la cola ni pierde el resumen."""

    def test_unexpected_exception_is_isolated(self, tmp_path: Path) -> None:
        requests = [
            _request(tmp_path, url="https://youtu.be/ok1"),
            _request(tmp_path, url="https://youtu.be/boom"),
            _request(tmp_path, url="https://youtu.be/ok1"),  # URL duplicada a propósito
        ]
        seen: list[tuple[int, DownloadStatus]] = []

        summary = asyncio.run(
            DownloadQueue(_FlakyDownloader(), max_concurrent=2).run_all(
                requests, on_result=lambda i, r: seen.append((i, r.status))
            )
        )

        assert (summary.total, summary.completed, summary.failed) == (3, 2, 1)
        assert sorted(seen) == [
            (0, DownloadStatus.COMPLETED),
            (1, DownloadStatus.FAILED),
            (2, DownloadStatus.COMPLETED),
        ]

    def test_cancelling_the_queue_cancels_the_downloader(self, tmp_path: Path) -> None:
        downloader = _FlakyDownloader()

        async def scenario() -> None:
            task = asyncio.create_task(
                DownloadQueue(downloader, max_concurrent=1).run_all(
                    [_request(tmp_path, url="https://youtu.be/ok")]
                )
            )
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())
        assert downloader.cancelled


class TestDependencies:
    def test_yt_dlp_age_is_computed_from_date_version(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import date

        monkeypatch.setattr("importlib.metadata.version", lambda name: "2026.08.19")
        info = dependencies.yt_dlp_version_info(today=date(2026, 10, 5))
        assert info is not None
        assert info.age_days == 47

    def test_find_js_runtime(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            dependencies.shutil, "which", lambda b: "/usr/bin/node" if b == "node" else None
        )
        assert dependencies.find_js_runtime() == "node"
        monkeypatch.setattr(dependencies.shutil, "which", lambda b: None)
        assert dependencies.find_js_runtime() is None
