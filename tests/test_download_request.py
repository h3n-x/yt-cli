from pathlib import Path

import pytest
from pydantic import ValidationError

from yt_cli.models.download_request import DownloadRequest
from yt_cli.models.enums import DownloadKind


def _base_kwargs(tmp_path: Path) -> dict:
    return {
        "url": "https://www.youtube.com/watch?v=abc123",
        "kind": DownloadKind.VIDEO,
        "output_directory": tmp_path,
        "filename_template": "{title}.{ext}",
    }


class TestDownloadRequestValidation:
    def test_valid_request_is_constructed(self, tmp_path: Path) -> None:
        request = DownloadRequest(**_base_kwargs(tmp_path))
        assert request.kind is DownloadKind.VIDEO

    def test_rejects_invalid_url(self, tmp_path: Path) -> None:
        kwargs = _base_kwargs(tmp_path)
        kwargs["url"] = "https://evil.com/video"
        with pytest.raises(ValidationError):
            DownloadRequest(**kwargs)

    def test_expands_output_directory(self, tmp_path: Path) -> None:
        kwargs = _base_kwargs(tmp_path)
        kwargs["output_directory"] = "~/some/dir"
        request = DownloadRequest(**kwargs)
        assert "~" not in str(request.output_directory)
        assert request.output_directory.is_absolute()

    def test_default_subtitle_languages_is_empty_list(self, tmp_path: Path) -> None:
        request = DownloadRequest(**_base_kwargs(tmp_path))
        assert request.subtitle_languages == []

    def test_rejects_template_with_unknown_placeholder(self, tmp_path: Path) -> None:
        """Corrige B5 de AUDIT_REPORT.md: antes esto solo fallaba en tiempo de
        ejecución dentro de yt-dlp; ahora falla rápido con ValidationError.
        """
        kwargs = _base_kwargs(tmp_path)
        kwargs["filename_template"] = "{uploader}/{tittle}.{ext}"  # typo deliberado
        with pytest.raises(ValidationError):
            DownloadRequest(**kwargs)

    def test_accepts_all_documented_placeholders(self, tmp_path: Path) -> None:
        kwargs = _base_kwargs(tmp_path)
        kwargs["filename_template"] = "{uploader}/{playlist}/{title}_{date}_{id}_{resolution}.{ext}"
        request = DownloadRequest(**kwargs)
        assert "{uploader}" in request.filename_template
