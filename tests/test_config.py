from pathlib import Path

import pytest

from yt_cli.config.manager import ConfigError, load_config, save_config
from yt_cli.config.models import AppConfig
from yt_cli.models.enums import AudioQuality, OverwritePolicy, VideoFormat, VideoQuality


class TestAppConfigDefaults:
    def test_default_config_is_valid(self) -> None:
        config = AppConfig()
        assert config.downloads.video_format is VideoFormat.MP4
        assert config.downloads.video_quality is VideoQuality.P1080
        assert config.network.max_concurrent_downloads == 3

    def test_download_directory_defaults_under_home(self) -> None:
        config = AppConfig()
        assert config.general.download_directory.is_absolute()

    def test_download_directory_expands_user(self) -> None:
        config = AppConfig.model_validate({"general": {"download_directory": "~/videos"}})
        assert "~" not in str(config.general.download_directory)


class TestNetworkConfigValidation:
    def test_rejects_zero_concurrent_downloads(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 - error de validación de Pydantic
            AppConfig.model_validate({"network": {"max_concurrent_downloads": 0}})

    def test_rejects_excessive_concurrent_downloads(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            AppConfig.model_validate({"network": {"max_concurrent_downloads": 100}})


class TestProfiles:
    def test_resolve_downloads_without_profile_returns_global_defaults(self) -> None:
        config = AppConfig()
        assert config.resolve_downloads(None) is config.downloads

    def test_resolve_downloads_with_named_profile(self) -> None:
        config = AppConfig.model_validate(
            {
                "profiles": {
                    "archivo": {"audio_format": "flac", "audio_quality": "best"},
                }
            }
        )
        resolved = config.resolve_downloads("archivo")
        assert resolved.audio_format.value == "flac"
        assert resolved.audio_quality.value == "best"

    def test_resolve_downloads_with_unknown_profile_raises(self) -> None:
        config = AppConfig()
        with pytest.raises(KeyError, match="no existe"):
            config.resolve_downloads("no-existe")

    def test_profiles_round_trip_through_toml(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        original = AppConfig.model_validate({"profiles": {"movil": {"video_quality": "480p"}}})
        save_config(original, path=config_path)
        loaded = load_config(path=config_path)
        assert loaded.resolve_downloads("movil").video_quality.value == "480p"


class TestConfigPersistence:
    def test_round_trip_save_and_load(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        original = AppConfig()
        original.downloads.video_quality = VideoQuality.P720
        original.downloads.audio_quality = AudioQuality.K320
        original.downloads.overwrite_policy = OverwritePolicy.OVERWRITE
        original.network.max_concurrent_downloads = 8

        save_config(original, path=config_path)
        loaded = load_config(path=config_path)

        assert loaded.downloads.video_quality is VideoQuality.P720
        assert loaded.downloads.audio_quality is AudioQuality.K320
        assert loaded.downloads.overwrite_policy is OverwritePolicy.OVERWRITE
        assert loaded.network.max_concurrent_downloads == 8

    def test_missing_config_file_returns_defaults(self, tmp_path: Path) -> None:
        config = load_config(path=tmp_path / "does_not_exist.toml")
        assert config == AppConfig()

    def test_invalid_toml_raises_config_error(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "config.toml"
        bad_file.write_text("this is not [ valid toml", encoding="utf-8")

        with pytest.raises(ConfigError):
            load_config(path=bad_file)

    def test_invalid_values_raise_config_error(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "config.toml"
        bad_file.write_text("[network]\nmax_concurrent_downloads = 999\n", encoding="utf-8")

        with pytest.raises(ConfigError):
            load_config(path=bad_file)

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        nested_path = tmp_path / "a" / "b" / "config.toml"
        save_config(AppConfig(), path=nested_path)
        assert nested_path.exists()

    def test_round_trip_with_special_toml_characters(self, tmp_path: Path) -> None:
        """Verifica que valores con comillas, backslashes y saltos de línea no
        rompen ni permiten inyectar TOML arbitrario al serializar/deserializar
        (ver SECURITY_REPORT.md, punto 9).
        """
        config_path = tmp_path / "config.toml"
        original = AppConfig()
        hostile_template = "raro\"con'comillas\\y\nsalto_de_linea/{title}.{ext}"
        original.downloads.filename_template = hostile_template

        save_config(original, path=config_path)
        loaded = load_config(path=config_path)

        assert loaded.downloads.filename_template == hostile_template
