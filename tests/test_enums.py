from yt_cli.models.enums import AudioQuality, VideoQuality


class TestVideoQuality:
    def test_height_extracts_numeric_value(self) -> None:
        assert VideoQuality.P144.height == 144
        assert VideoQuality.P1080.height == 1080
        assert VideoQuality.P2160.height == 2160

    def test_best_has_no_height_limit(self) -> None:
        assert VideoQuality.BEST.height is None

    def test_as_yt_dlp_format_for_fixed_quality(self) -> None:
        assert (
            VideoQuality.P720.as_yt_dlp_format()
            == "bestvideo*[height<=720]+bestaudio/best[height<=720]"
        )

    def test_as_yt_dlp_format_for_best(self) -> None:
        assert VideoQuality.BEST.as_yt_dlp_format() == "bestvideo*+bestaudio/best"


class TestAudioQuality:
    def test_kbps_extracts_numeric_value(self) -> None:
        assert AudioQuality.K128.kbps == 128
        assert AudioQuality.K320.kbps == 320

    def test_best_has_no_kbps(self) -> None:
        assert AudioQuality.BEST.kbps is None
