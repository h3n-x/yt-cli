"""Tests de la CLI (config, perfiles, historial, update, search) vía CliRunner.

Cada test aísla su propio HOME de configuración/datos/cache vía variables de
entorno XDG_*, para no leer ni escribir en la configuración real de la
máquina que ejecute los tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from yt_cli.cli import main as cli_main
from yt_cli.cli import system_cmds
from yt_cli.core.downloader import DownloadError

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_xdg_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Evita que los tests toquen ~/.config, ~/.local/share o ~/.cache reales."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


class TestVersion:
    def test_version_command_prints_version(self) -> None:
        result = runner.invoke(cli_main.app, ["version"])
        assert result.exit_code == 0
        assert "yt-cli" in result.stdout

    def test_version_json_output_is_valid_json(self) -> None:
        import json

        result = runner.invoke(cli_main.app, ["version", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "yt-cli" in data

    def test_eager_version_flag_exits_before_running_subcommand(self) -> None:
        result = runner.invoke(cli_main.app, ["--version"])
        assert result.exit_code == 0
        assert "yt-cli" in result.stdout


class TestConfigCommands:
    def test_config_show_outputs_json(self) -> None:
        result = runner.invoke(cli_main.app, ["config", "show"])
        assert result.exit_code == 0
        assert "downloads" in result.stdout

    def test_config_set_and_show_round_trip(self) -> None:
        result = runner.invoke(cli_main.app, ["config", "set", "downloads.video_quality", "720p"])
        assert result.exit_code == 0

        result = runner.invoke(cli_main.app, ["config", "show"])
        assert "720p" in result.stdout

    def test_config_set_invalid_key_fails_cleanly(self) -> None:
        result = runner.invoke(cli_main.app, ["config", "set", "downloads.no_existe", "x"])
        assert result.exit_code == 1
        assert (
            "no es una ruta de configuración válida" in result.stdout
            or "no es una ruta" in result.output
        )

    def test_config_set_invalid_nested_path_fails_cleanly(self) -> None:
        """Antes esto lanzaba un AttributeError crudo (ver docs/history/AUDIT_REPORT.md)."""
        result = runner.invoke(cli_main.app, ["config", "set", "no_existe.campo", "x"])
        assert result.exit_code == 1

    def test_config_set_invalid_value_reports_validation_error(self) -> None:
        result = runner.invoke(
            cli_main.app, ["config", "set", "network.max_concurrent_downloads", "999"]
        )
        assert result.exit_code == 1

    def test_config_path_prints_a_path(self) -> None:
        result = runner.invoke(cli_main.app, ["config", "path"])
        assert result.exit_code == 0
        assert "config.toml" in result.stdout


class TestProfileCommands:
    def test_profile_list_empty(self) -> None:
        result = runner.invoke(cli_main.app, ["config", "profile", "list"])
        assert result.exit_code == 0
        assert "No hay perfiles" in result.stdout

    def test_profile_set_creates_profile(self) -> None:
        result = runner.invoke(
            cli_main.app, ["config", "profile", "set", "archivo", "audio_format", "flac"]
        )
        assert result.exit_code == 0

        result = runner.invoke(cli_main.app, ["config", "profile", "show", "archivo"])
        assert result.exit_code == 0
        assert "flac" in result.stdout

    def test_profile_list_shows_created_profile(self) -> None:
        runner.invoke(cli_main.app, ["config", "profile", "set", "rapido", "video_quality", "480p"])
        result = runner.invoke(cli_main.app, ["config", "profile", "list"])
        assert "rapido" in result.stdout

    def test_profile_set_invalid_field_fails(self) -> None:
        result = runner.invoke(
            cli_main.app, ["config", "profile", "set", "x", "campo_inexistente", "y"]
        )
        assert result.exit_code == 1

    def test_profile_show_unknown_fails(self) -> None:
        result = runner.invoke(cli_main.app, ["config", "profile", "show", "no-existe"])
        assert result.exit_code == 1

    def test_profile_remove(self) -> None:
        runner.invoke(
            cli_main.app, ["config", "profile", "set", "temporal", "audio_format", "opus"]
        )
        result = runner.invoke(cli_main.app, ["config", "profile", "remove", "temporal"])
        assert result.exit_code == 0

        result = runner.invoke(cli_main.app, ["config", "profile", "list"])
        assert "temporal" not in result.stdout

    def test_remove_unknown_profile_fails(self) -> None:
        result = runner.invoke(cli_main.app, ["config", "profile", "remove", "no-existe"])
        assert result.exit_code == 1

    def test_download_with_unknown_profile_fails_cleanly(self) -> None:
        result = runner.invoke(
            cli_main.app, ["--profile", "no-existe", "download", "https://youtu.be/abc123"]
        )
        assert result.exit_code == 1


class TestHistoryCommands:
    def test_history_empty(self) -> None:
        result = runner.invoke(cli_main.app, ["history"])
        assert result.exit_code == 0
        assert "vacío" in result.stdout

    def test_history_json_empty_is_empty_array(self) -> None:
        import json

        result = runner.invoke(cli_main.app, ["history", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.stdout) == []

    def test_history_export_json(self, tmp_path: Path) -> None:
        destination = tmp_path / "out.json"
        result = runner.invoke(cli_main.app, ["history", "export", str(destination)])
        assert result.exit_code == 0
        assert destination.exists()

    def test_history_export_invalid_format_fails(self, tmp_path: Path) -> None:
        result = runner.invoke(
            cli_main.app, ["history", "export", str(tmp_path / "x.txt"), "--format", "xml"]
        )
        assert result.exit_code == 2  # error de uso de Click: valor fuera del enum

    def test_history_clear_with_yes_flag(self) -> None:
        result = runner.invoke(cli_main.app, ["history", "clear", "--yes"])
        assert result.exit_code == 0


class TestDownloadValidation:
    """Estas pruebas no llegan a invocar yt-dlp real: la URL falla en
    validación de Pydantic antes de construir el downloader.
    """

    def test_download_rejects_unsupported_host(self) -> None:
        result = runner.invoke(cli_main.app, ["download", "https://vimeo.com/12345"])
        assert result.exit_code == 1

    def test_download_rejects_non_http_scheme(self) -> None:
        result = runner.invoke(cli_main.app, ["download", "javascript:alert(1)"])
        assert result.exit_code == 1

    def test_audio_rejects_unsupported_host(self) -> None:
        result = runner.invoke(cli_main.app, ["audio", "https://vimeo.com/12345"])
        assert result.exit_code == 1


class TestDoctor:
    def test_doctor_runs_without_crashing(self) -> None:
        # No se mockea nada: doctor debe poder ejecutarse siempre, exit_code
        # 0 o 1 según si ffmpeg está disponible en la máquina de CI, pero
        # nunca debe lanzar una excepción no controlada.
        result = runner.invoke(cli_main.app, ["doctor"])
        assert result.exit_code in (0, 1)
        assert result.exception is None or isinstance(result.exception, SystemExit)


def _pretend_pip_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system_cmds, "_installer", lambda: "pip")
    monkeypatch.setattr(system_cmds, "_is_externally_managed", lambda: False)


class TestUpdateCommands:
    def test_update_reports_up_to_date(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_cmds, "_current_version", lambda: "1.0.0")
        monkeypatch.setattr(system_cmds, "_fetch_latest_pypi_version", lambda name: "1.0.0")
        result = runner.invoke(cli_main.app, ["update"])
        assert result.exit_code == 0
        assert "última versión" in result.stdout

    def test_update_reports_new_version_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(system_cmds, "_current_version", lambda: "1.0.0")
        monkeypatch.setattr(system_cmds, "_fetch_latest_pypi_version", lambda name: "2.0.0")
        result = runner.invoke(cli_main.app, ["update"])
        assert result.exit_code == 0
        assert "2.0.0" in result.stdout

    def test_update_handles_package_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(name: str) -> str:
            raise LookupError(f"El paquete '{name}' no está publicado en PyPI todavía.")

        monkeypatch.setattr(system_cmds, "_fetch_latest_pypi_version", _raise)
        result = runner.invoke(cli_main.app, ["update"])
        assert result.exit_code == 1

    def test_self_update_skips_pip_when_already_current(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _pretend_pip_install(monkeypatch)
        monkeypatch.setattr(system_cmds, "_current_version", lambda: "1.0.0")
        monkeypatch.setattr(system_cmds, "_fetch_latest_pypi_version", lambda name: "1.0.0")
        subprocess_mock = MagicMock()
        monkeypatch.setattr(system_cmds.subprocess, "run", subprocess_mock)

        result = runner.invoke(cli_main.app, ["self-update"])

        assert result.exit_code == 0
        subprocess_mock.assert_not_called()

    def test_self_update_calls_pip_with_fixed_argument_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifica que self-update nunca construye un comando de shell: debe
        llamar a subprocess.run con una lista de argumentos fija y una versión
        exacta (la que se comprobó en PyPI).
        """
        _pretend_pip_install(monkeypatch)
        monkeypatch.setattr(system_cmds, "_current_version", lambda: "1.0.0")
        monkeypatch.setattr(system_cmds, "_fetch_latest_pypi_version", lambda name: "2.0.0")
        subprocess_mock = MagicMock()
        subprocess_mock.return_value.returncode = 0
        monkeypatch.setattr(system_cmds.subprocess, "run", subprocess_mock)

        result = runner.invoke(cli_main.app, ["self-update", "--yes"])

        assert result.exit_code == 0
        args, kwargs = subprocess_mock.call_args
        assert isinstance(args[0], list)
        assert kwargs.get("shell", False) is False
        assert "pip" in args[0]
        assert "yt-cli==2.0.0" in args[0]


class TestSearchJson:
    def test_search_json_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import json

        fake_info = {
            "entries": [
                {
                    "title": "Video de prueba",
                    "uploader": "Canal X",
                    "duration": 125,
                    "view_count": 1000,
                    "webpage_url": "https://youtu.be/abc123",
                }
            ]
        }
        monkeypatch.setattr(
            "yt_cli.core.downloader.YtDlpDownloader.extract_metadata_only",
            lambda self, url, **kwargs: fake_info,
        )

        result = runner.invoke(cli_main.app, ["search", "test query", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data[0]["title"] == "Video de prueba"

    def test_search_handles_no_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "yt_cli.core.downloader.YtDlpDownloader.extract_metadata_only",
            lambda self, url, **kwargs: {"entries": []},
        )
        result = runner.invoke(cli_main.app, ["search", "sin resultados"])
        assert result.exit_code == 0
        assert "Sin resultados" in result.stdout

    def test_search_handles_extraction_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(self, url: str, **kwargs: object) -> None:  # noqa: ANN001
            raise DownloadError("fallo simulado de red")

        monkeypatch.setattr("yt_cli.core.downloader.YtDlpDownloader.extract_metadata_only", _raise)
        result = runner.invoke(cli_main.app, ["search", "algo"])
        assert result.exit_code == 1
