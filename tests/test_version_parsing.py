"""Tests de `_parse_version` (comparación de versiones para update/self-update)."""

from __future__ import annotations

import pytest

from yt_cli.cli.system_cmds import _parse_version


class TestParseVersion:
    @pytest.mark.parametrize(
        ("older", "newer"),
        [
            ("1.9.9", "2.0.0"),
            ("0.3.1", "0.4.0"),
            ("1.0.0rc1", "1.0.0"),
            ("1.0.0b2", "1.0.0rc1"),
            ("2.1.3-beta", "2.1.3"),
            ("1.0", "1.0.1"),
            ("9.0.0", "10.0.0"),
        ],
    )
    def test_ordering(self, older: str, newer: str) -> None:
        assert _parse_version(older) < _parse_version(newer)

    @pytest.mark.parametrize(
        ("a", "b"), [("1.0.0", "1.0.0"), ("1.0.0+dev", "1.0.0"), ("1.0", "1.0.0")]
    )
    def test_equivalent_versions_compare_equal(self, a: str, b: str) -> None:
        assert _parse_version(a) == _parse_version(b)

    def test_garbage_sorts_lowest(self) -> None:
        assert _parse_version("no-es-una-version") < _parse_version("0.0.1")
