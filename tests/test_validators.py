from pathlib import Path

import pytest

from yt_cli.core.validators import (
    InvalidURLError,
    UnsafePathError,
    resolve_safe_path,
    validate_url,
    validate_urls,
)


class TestValidateURL:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ],
    )
    def test_accepts_valid_youtube_urls(self, url: str) -> None:
        assert validate_url(url) == url

    def test_strips_surrounding_whitespace(self) -> None:
        assert validate_url("  https://youtu.be/abc  ") == "https://youtu.be/abc"

    def test_rejects_empty_url(self) -> None:
        with pytest.raises(InvalidURLError):
            validate_url("")

    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(InvalidURLError):
            validate_url("javascript:alert(1)")

    def test_rejects_file_scheme(self) -> None:
        with pytest.raises(InvalidURLError):
            validate_url("file:///etc/passwd")

    def test_rejects_unsupported_host(self) -> None:
        with pytest.raises(InvalidURLError):
            validate_url("https://evil-tracker.example.com/watch?v=abc")

    def test_rejects_host_that_merely_contains_youtube(self) -> None:
        """youtube.com.evil.com no debe pasar por 'contener' la palabra youtube."""
        with pytest.raises(InvalidURLError):
            validate_url("https://youtube.com.evil.com/watch?v=abc")

    def test_rejects_missing_host(self) -> None:
        with pytest.raises(InvalidURLError):
            validate_url("https:///watch?v=abc")


class TestValidateURLs:
    def test_validates_all_urls_in_list(self) -> None:
        urls = ["https://youtu.be/a", "https://youtu.be/b"]
        assert validate_urls(urls) == urls

    def test_error_message_includes_index(self) -> None:
        with pytest.raises(InvalidURLError, match="URL #2"):
            validate_urls(["https://youtu.be/a", "not-a-url"])


class TestResolveSafePath:
    def test_resolves_normal_relative_path(self, tmp_path: Path) -> None:
        result = resolve_safe_path(tmp_path, "canal/video.mp4")
        assert result == (tmp_path / "canal" / "video.mp4").resolve()

    def test_rejects_parent_directory_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(UnsafePathError):
            resolve_safe_path(tmp_path, "../../etc/passwd")

    def test_rejects_absolute_path_escape(self, tmp_path: Path) -> None:
        with pytest.raises(UnsafePathError):
            resolve_safe_path(tmp_path, "../outside")

    def test_rejects_symlink_escaping_base_directory(self, tmp_path: Path) -> None:
        """Un symlink dentro del árbol de descarga que apunte fuera del
        directorio base no debe poder usarse para escribir fuera de él:
        Path.resolve() sigue el symlink antes de comparar contra la base.
        """
        outside = tmp_path.parent / "outside_target"
        outside.mkdir(exist_ok=True)
        base = tmp_path / "base"
        base.mkdir()
        symlink = base / "escape_link"
        symlink.symlink_to(outside, target_is_directory=True)

        with pytest.raises(UnsafePathError):
            resolve_safe_path(base, "escape_link/payload.mp4")
