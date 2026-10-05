"""Tests de yt_cli.cli.main._parse_version.

A diferencia del resto de tests/test_cli.py, esta función es puro-stdlib
(no depende de typer/pydantic/rich en su lógica interna, solo en que el
módulo que la contiene las importe), así que se probó también con una
verificación manual directa en esta sesión (ver TEST_REPORT.md) además de
quedar aquí como test formal de pytest.
"""

from __future__ import annotations

import pytest

from yt_cli.cli.main import _parse_version


class TestParseVersion:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0.2.0", (0, 2, 0)),
            ("1.0.0", (1, 0, 0)),
            ("0.0.0+dev", (0, 0, 0)),
            ("2.1.3-beta", (2, 1, 3)),
            ("10.20.30", (10, 20, 30)),
        ],
    )
    def test_parses_semver_like_strings(self, raw: str, expected: tuple[int, ...]) -> None:
        assert _parse_version(raw) == expected

    def test_newer_version_compares_greater(self) -> None:
        assert _parse_version("2.0.0") > _parse_version("1.9.9")

    def test_equal_versions_compare_equal(self) -> None:
        assert _parse_version("1.0.0") == _parse_version("1.0.0")

    def test_dev_suffix_ignored_in_comparison(self) -> None:
        assert _parse_version("1.0.0+dev") == _parse_version("1.0.0")
