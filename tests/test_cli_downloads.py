"""Tests de la CLI de descarga de extremo a extremo, con un downloader falso.

Cubren la orquestación que antes no tenía tests (`audio`/`playlist`/`batch`),
los códigos de salida y que cada error se muestre una sola vez.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from yt_cli.cli import download_cmds, system_cmds
from yt_cli.cli import main as cli_main
from yt_cli.cli._app import EXIT_INTERRUPTED, EXIT_PARTIAL
from yt_cli.config.manager import config_file_path, load_config
from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import AudioFormat, DownloadStatus, MediaType, Scope
from yt_cli.models.results import DownloadResult, EntryResult
from yt_cli.services.history import HistoryStore

runner = CliRunner()
PLAYLIST_URL = "https://music.youtube.com/playlist?list=PLJnszpL2Ww1pprYTSmZANQgJErUcCY59T&si=8pQN"
UNAVAILABLE = (
    "eRGbT2uxj4g: Video unavailable — "
    "El video fue eliminado, es privado o no está disponible en tu región."
)


@pytest.fixture(autouse=True)
def isolated_xdg_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


class FakeDownloader:
    def __init__(self, behaviour: Any = None) -> None:
        self.requests: list[DownloadRequest] = []
        self.behaviour = behaviour or _complete
        self.cancelled = False

    def download(self, request: DownloadRequest, progress_callback: Any = None) -> DownloadResult:
        self.requests.append(request)
        return self.behaviour(request)

    def cancel(self) -> None:
        self.cancelled = True


def _complete(request: DownloadRequest) -> DownloadResult:
    return DownloadResult(
        request=request,
        status=DownloadStatus.COMPLETED,
        output_path=request.output_directory / "video.mp4",
        title="Video",
    )


def _partial_playlist(request: DownloadRequest) -> DownloadResult:
    entries = [
        EntryResult(
            status=DownloadStatus.COMPLETED,
            title="5. Por Mi Es Que Te Mueres",
            url="https://www.youtube.com/watch?v=aaa",
            output_path=request.output_directory / "a.mp3",
        ),
        EntryResult(
            status=DownloadStatus.FAILED,
            title=None,
            url="https://www.youtube.com/watch?v=eRGbT2uxj4g",
            output_path=None,
            error_message=UNAVAILABLE,
        ),
        EntryResult(
            status=DownloadStatus.COMPLETED,
            title="7. Otra",
            url="https://www.youtube.com/watch?v=ccc",
            output_path=request.output_directory / "c.mp3",
        ),
    ]
    return DownloadResult(
        request=request,
        status=DownloadStatus.PARTIAL,
        output_path=request.output_directory,
        title="Pa' Que Te Enamores",
        error_message="1/3 entradas fallaron.",
        entry_count=3,
        entry_failures=1,
        entries=entries,
    )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDownloader:
    downloader = FakeDownloader()
    monkeypatch.setattr(download_cmds, "build_downloader", lambda config: downloader)
    monkeypatch.setattr(download_cmds, "require_ffmpeg", lambda: None)
    monkeypatch.setattr(download_cmds, "find_js_runtime", lambda: "deno")
    return downloader


class TestUserReportedPlaylist:
    """El comando exacto del reporte: `yt-cli audio "<playlist de YouTube Music>"`."""

    def test_audio_on_playlist_url_downloads_whole_playlist_as_audio(
        self, fake: FakeDownloader
    ) -> None:
        fake.behaviour = _partial_playlist
        result = runner.invoke(cli_main.app, ["audio", PLAYLIST_URL])

        request = fake.requests[0]
        assert request.media is MediaType.AUDIO
        assert request.scope is Scope.PLAYLIST
        assert result.exit_code == EXIT_PARTIAL
        assert "2 descargadas" in result.stdout
        assert "1 fallidas" in result.stdout

    def test_each_error_is_reported_exactly_once_without_ansi_residue(
        self, fake: FakeDownloader
    ) -> None:
        fake.behaviour = _partial_playlist
        result = runner.invoke(cli_main.app, ["audio", PLAYLIST_URL])
        output = result.stdout + (result.stderr if result.stderr_bytes else "")

        assert output.count("Video unavailable") == 1
        assert "[1m" not in output and "\x1b[0;31m" not in output

    def test_history_has_one_row_per_video(self, fake: FakeDownloader) -> None:
        fake.behaviour = _partial_playlist
        runner.invoke(cli_main.app, ["audio", PLAYLIST_URL])

        rows = HistoryStore().list_all()
        assert len(rows) == 3
        assert {r.url for r in rows} == {
            "https://www.youtube.com/watch?v=aaa",
            "https://www.youtube.com/watch?v=eRGbT2uxj4g",
            "https://www.youtube.com/watch?v=ccc",
        }

    def test_history_failed_lists_cause(self, fake: FakeDownloader) -> None:
        fake.behaviour = _partial_playlist
        runner.invoke(cli_main.app, ["audio", PLAYLIST_URL])
        result = runner.invoke(cli_main.app, ["history", "--failed", "--json"])
        rows = json.loads(result.stdout)
        assert len(rows) == 1
        assert "Video unavailable" in rows[0]["error_message"]


class TestCollectionOptions:
    def test_playlist_audio_with_format_and_quality(self, fake: FakeDownloader) -> None:
        result = runner.invoke(
            cli_main.app,
            ["playlist", PLAYLIST_URL, "--audio", "-f", "opus", "-q", "best", "--items", "1:5"],
        )
        assert result.exit_code == 0, result.stdout
        request = fake.requests[0]
        assert request.media is MediaType.AUDIO
        assert request.audio_format is AudioFormat.OPUS
        assert request.playlist_items == "1:5"

    def test_playlist_rejects_audio_format_without_audio_flag(self, fake: FakeDownloader) -> None:
        result = runner.invoke(cli_main.app, ["playlist", PLAYLIST_URL, "-f", "opus"])
        assert result.exit_code == 1
        assert fake.requests == []

    def test_archive_flag_sets_archive_path(self, fake: FakeDownloader) -> None:
        runner.invoke(cli_main.app, ["audio", PLAYLIST_URL, "--archive"])
        archive = fake.requests[0].download_archive
        assert archive is not None
        assert archive.name == "archive.txt"

    def test_archive_from_config(self, fake: FakeDownloader) -> None:
        runner.invoke(cli_main.app, ["config", "set", "downloads.use_download_archive", "true"])
        runner.invoke(cli_main.app, ["audio", PLAYLIST_URL])
        assert fake.requests[0].download_archive is not None

    def test_collection_uses_playlist_template(self, fake: FakeDownloader) -> None:
        runner.invoke(cli_main.app, ["audio", PLAYLIST_URL])
        assert "{playlist}" in fake.requests[0].filename_template


class TestSingleDownloads:
    def test_success(self, fake: FakeDownloader) -> None:
        result = runner.invoke(cli_main.app, ["download", "https://youtu.be/abc"])
        assert result.exit_code == 0
        assert fake.requests[0].scope is Scope.SINGLE

    def test_failure_exit_code_and_single_message(self, fake: FakeDownloader) -> None:
        def failed(request: DownloadRequest) -> DownloadResult:
            return DownloadResult(
                request=request,
                status=DownloadStatus.FAILED,
                output_path=None,
                title=None,
                error_message=UNAVAILABLE,
            )

        fake.behaviour = failed
        result = runner.invoke(cli_main.app, ["audio", "https://youtu.be/eRGbT2uxj4g"])
        assert result.exit_code == 1
        assert (result.stdout + result.stderr).count("Video unavailable") == 1

    def test_ctrl_c_exits_130(self, fake: FakeDownloader) -> None:
        def interrupted(request: DownloadRequest) -> DownloadResult:
            raise KeyboardInterrupt

        fake.behaviour = interrupted
        result = runner.invoke(cli_main.app, ["download", "https://youtu.be/abc"])
        assert result.exit_code == EXIT_INTERRUPTED
        assert fake.cancelled

    def test_missing_ffmpeg_fails_before_downloading(
        self, fake: FakeDownloader, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from yt_cli.core.dependencies import FFmpegNotFoundError

        def missing() -> None:
            raise FFmpegNotFoundError("'ffmpeg' no se encontró en PATH.")

        monkeypatch.setattr(download_cmds, "require_ffmpeg", missing)
        result = runner.invoke(cli_main.app, ["download", "https://youtu.be/abc"])
        assert result.exit_code == 1
        assert fake.requests == []

    def test_missing_js_runtime_warns(
        self, fake: FakeDownloader, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(download_cmds, "find_js_runtime", lambda: None)
        result = runner.invoke(cli_main.app, ["download", "https://youtu.be/abc"])
        assert result.exit_code == 0
        assert "deno" in result.stdout

    def test_invalid_template_is_a_clean_error(self, fake: FakeDownloader) -> None:
        result = runner.invoke(
            cli_main.app, ["download", "https://youtu.be/abc", "--template", "{title.__class__}"]
        )
        assert result.exit_code == 1
        assert "no soportado" in result.stderr


class TestBatch:
    def test_duplicate_urls_each_get_a_result(self, fake: FakeDownloader, tmp_path: Path) -> None:
        urls = tmp_path / "urls.txt"
        urls.write_text("https://youtu.be/a\n# comentario\nhttps://youtu.be/a\n\n")
        result = runner.invoke(cli_main.app, ["batch", str(urls)])
        assert result.exit_code == 0, result.stdout
        assert len(fake.requests) == 2
        assert "2/2 completadas" in result.stdout

    def test_missing_file_is_usage_error(self, tmp_path: Path) -> None:
        result = runner.invoke(cli_main.app, ["batch", str(tmp_path / "no-existe.txt")])
        assert result.exit_code == 2

    def test_directory_is_usage_error(self, tmp_path: Path) -> None:
        result = runner.invoke(cli_main.app, ["batch", str(tmp_path)])
        assert result.exit_code == 2

    def test_failures_listed_and_exit_1(self, fake: FakeDownloader, tmp_path: Path) -> None:
        def fail_b(request: DownloadRequest) -> DownloadResult:
            if request.url.endswith("/b"):
                return DownloadResult(
                    request=request,
                    status=DownloadStatus.FAILED,
                    output_path=None,
                    title=None,
                    error_message="b: Private video",
                )
            return _complete(request)

        fake.behaviour = fail_b
        urls = tmp_path / "urls.txt"
        urls.write_text("https://youtu.be/a\nhttps://youtu.be/b\n")
        result = runner.invoke(cli_main.app, ["batch", str(urls), "--audio"])
        assert result.exit_code == 1
        assert "b: Private video" in result.stdout
        assert all(r.media is MediaType.AUDIO for r in fake.requests)


class TestSearchCache:
    def test_second_search_uses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def extract(self: object, url: str, **kwargs: object) -> dict[str, Any]:
            calls.append(url)
            return {"entries": [{"title": "T", "url": "https://youtu.be/x"}]}

        monkeypatch.setattr("yt_cli.core.downloader.YtDlpDownloader.extract_metadata_only", extract)
        runner.invoke(cli_main.app, ["search", "algo", "--json"])
        result = runner.invoke(cli_main.app, ["search", "algo", "--json"])
        assert json.loads(result.stdout)[0]["title"] == "T"
        assert len(calls) == 1

    def test_cache_disabled_by_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        def extract(self: object, url: str, **kwargs: object) -> dict[str, Any]:
            calls.append(url)
            return {"entries": []}

        monkeypatch.setattr("yt_cli.core.downloader.YtDlpDownloader.extract_metadata_only", extract)
        runner.invoke(cli_main.app, ["config", "set", "general.cache_enabled", "false"])
        runner.invoke(cli_main.app, ["search", "algo", "--json"])
        runner.invoke(cli_main.app, ["search", "algo", "--json"])
        assert len(calls) == 2


class TestConfigCommandsExtended:
    def test_config_file_is_private(self) -> None:
        runner.invoke(cli_main.app, ["config", "set", "network.retries", "5"])
        mode = stat.S_IMODE(os.stat(config_file_path()).st_mode)
        assert mode == 0o600

    def test_proxy_credentials_are_masked_in_show(self) -> None:
        runner.invoke(
            cli_main.app, ["config", "set", "network.proxy", "http://user:secreto@proxy:3128"]
        )
        result = runner.invoke(cli_main.app, ["config", "show"])
        assert "secreto" not in result.stdout
        assert "***:***@proxy:3128" in result.stdout

    def test_none_resets_optional_value(self) -> None:
        runner.invoke(cli_main.app, ["config", "set", "network.rate_limit_kbps", "500"])
        runner.invoke(cli_main.app, ["config", "set", "network.rate_limit_kbps", "none"])
        assert load_config().network.rate_limit_kbps is None

    def test_sponsorblock_comma_list(self) -> None:
        result = runner.invoke(
            cli_main.app, ["config", "set", "downloads.sponsorblock_remove", "sponsor,selfpromo"]
        )
        assert result.exit_code == 0
        assert load_config().downloads.sponsorblock_remove == ["sponsor", "selfpromo"]

    def test_sponsorblock_unknown_category_fails(self) -> None:
        result = runner.invoke(
            cli_main.app, ["config", "set", "downloads.sponsorblock_remove", "anuncios"]
        )
        assert result.exit_code == 1

    def test_cookies_browser_validated(self) -> None:
        ok = runner.invoke(
            cli_main.app, ["config", "set", "network.cookies_from_browser", "firefox"]
        )
        bad = runner.invoke(
            cli_main.app, ["config", "set", "network.cookies_from_browser", "netscape"]
        )
        assert ok.exit_code == 0
        assert bad.exit_code == 1

    def test_ytdlp_passthrough_values_are_typed(self) -> None:
        runner.invoke(cli_main.app, ["config", "set", "ytdlp.geo_bypass_country", "ES"])
        runner.invoke(cli_main.app, ["config", "set", "ytdlp.sleep_interval", "2"])
        cfg = load_config()
        assert cfg.ytdlp == {"geo_bypass_country": "ES", "sleep_interval": 2}
        runner.invoke(cli_main.app, ["config", "set", "ytdlp.sleep_interval", "none"])
        assert "sleep_interval" not in load_config().ytdlp

    def test_unknown_section_fails_cleanly(self) -> None:
        result = runner.invoke(cli_main.app, ["config", "set", "profiles.x", "1"])
        assert result.exit_code == 1

    def test_history_export_refuses_to_overwrite(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        target.write_text("importante")
        result = runner.invoke(cli_main.app, ["history", "export", str(target)])
        assert result.exit_code == 1
        assert target.read_text() == "importante"
        forced = runner.invoke(cli_main.app, ["history", "export", str(target), "--force"])
        assert forced.exit_code == 0


class TestSelfUpdateSafety:
    """S1/S4: nunca instalar con pip algo que no sea este proyecto, ni sobre
    un Python gestionado por la distribución.
    """

    def test_refuses_when_not_installed_with_pip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_cmds, "_installer", lambda: None)
        run_mock: list[object] = []
        monkeypatch.setattr(system_cmds.subprocess, "run", lambda *a, **k: run_mock.append(a))
        result = runner.invoke(cli_main.app, ["self-update", "--yes"])
        assert result.exit_code == 1
        assert run_mock == []
        assert "gestor de paquetes" in result.stderr

    def test_refuses_on_externally_managed_python(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_cmds, "_installer", lambda: "pip")
        monkeypatch.setattr(system_cmds, "_is_externally_managed", lambda: True)
        result = runner.invoke(cli_main.app, ["self-update", "--yes"])
        assert result.exit_code == 1
        assert "PEP 668" in result.stderr

    def _fake_pypi(self, monkeypatch: pytest.MonkeyPatch, project_urls: dict[str, str]) -> None:
        import httpx

        class Response:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return {"info": {"version": "9.9.9", "project_urls": project_urls}}

        monkeypatch.setattr(httpx, "get", lambda *a, **k: Response())

    def test_pypi_package_from_another_project_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._fake_pypi(monkeypatch, {"Source": "https://github.com/atacante/yt-cli"})
        with pytest.raises(LookupError, match="no pertenece"):
            system_cmds._fetch_latest_pypi_version("yt-cli")

    def test_pypi_package_from_this_project_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._fake_pypi(monkeypatch, {"Source": "https://github.com/h3n-x/yt-cli"})
        assert system_cmds._fetch_latest_pypi_version("yt-cli") == "9.9.9"


class TestDoctor:
    def test_missing_js_runtime_is_a_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_cmds, "find_js_runtime", lambda: None)
        result = runner.invoke(cli_main.app, ["doctor"])
        assert result.exit_code == 1
        assert "runtime JavaScript" in result.stdout

    def test_reports_mutagen(self) -> None:
        result = runner.invoke(cli_main.app, ["doctor"])
        assert "mutagen" in result.stdout


class TestShellCompletion:
    """H3: los scripts empaquetados deben usar el protocolo de Typer."""

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_packaged_scripts_use_typer_protocol(self, shell: str) -> None:
        script = Path(__file__).parents[1] / "packaging" / "completions" / f"yt-cli.{shell}"
        assert f"_YT_CLI_COMPLETE=complete_{shell}" in script.read_text()

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_packaged_scripts_match_generator(self, shell: str) -> None:
        import importlib.util

        root = Path(__file__).parents[1] / "packaging"
        spec = importlib.util.spec_from_file_location("gen", root / "generate_completions.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert (root / "completions" / f"yt-cli.{shell}").read_text() == module.render(shell)

    def test_completion_protocol_answers(self) -> None:
        executable = Path(sys.executable).parent / "yt-cli"
        if not executable.exists():
            pytest.skip("yt-cli no está instalado en este entorno")
        env = dict(
            os.environ, _YT_CLI_COMPLETE="complete_bash", COMP_WORDS="yt-cli conf", COMP_CWORD="1"
        )
        output = subprocess.run(  # noqa: S603
            [str(executable)], env=env, capture_output=True, text=True, check=False, timeout=30
        )
        assert "config" in output.stdout.split()


class TestConfigContract:
    """A4: ningún campo de configuración puede quedar sin efecto."""

    def test_every_config_field_is_used_outside_config_package(self) -> None:
        from yt_cli.config.models import AppConfig, DownloadDefaults, GeneralConfig, NetworkConfig

        src = Path(__file__).parents[1] / "src" / "yt_cli"
        code = "\n".join(
            p.read_text() for p in src.rglob("*.py") if "config" not in p.relative_to(src).parts[:1]
        )
        fields = [
            *GeneralConfig.model_fields,
            *DownloadDefaults.model_fields,
            *NetworkConfig.model_fields,
            *AppConfig.model_fields,
        ]
        # `downloads` se consume a través de AppConfig.resolve_downloads().
        used_indirectly = {"downloads"}
        unused = [
            name
            for name in fields
            if name not in used_indirectly and f".{name}" not in code and f"{name}=" not in code
        ]
        assert unused == []


class TestCollectionTotalFailure:
    def test_failure_before_listing_entries_shows_only_the_error(
        self, fake: FakeDownloader
    ) -> None:
        def failed(request: DownloadRequest) -> DownloadResult:
            return DownloadResult(
                request=request,
                status=DownloadStatus.FAILED,
                output_path=None,
                title=None,
                error_message="PLx: Unable to download API page",
            )

        fake.behaviour = failed
        result = runner.invoke(cli_main.app, ["audio", PLAYLIST_URL])
        assert result.exit_code == 1
        assert "descargadas" not in result.stdout
        assert "Unable to download API page" in result.stderr
