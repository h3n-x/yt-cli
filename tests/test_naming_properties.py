"""Property-based tests para utils/naming.py, usando Hypothesis."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from yt_cli.utils.naming import render_filename_template, sanitize_filename

_FORBIDDEN_CHARS = set('<>:"/\\|?*')


@given(st.text())
def test_sanitize_filename_never_contains_forbidden_characters(raw: str) -> None:
    result = sanitize_filename(raw)
    assert not (_FORBIDDEN_CHARS & set(result))


@given(st.text())
def test_sanitize_filename_never_returns_empty_string(raw: str) -> None:
    assert sanitize_filename(raw) != ""


@given(st.text())
def test_sanitize_filename_is_idempotent(raw: str) -> None:
    """Sanear un nombre ya saneado no debe cambiarlo más: es un punto fijo."""
    once = sanitize_filename(raw)
    twice = sanitize_filename(once)
    assert once == twice


@given(st.text())
def test_sanitize_filename_respects_max_length(raw: str) -> None:
    result = sanitize_filename(raw)
    assert len(result) <= 200


@given(st.text(), st.text(), st.text())
def test_render_filename_template_never_raises_for_known_placeholders(
    title: str, uploader: str, ext: str
) -> None:
    """Con placeholders válidos, cualquier valor de metadato (incluyendo
    caracteres hostiles como '../' o control chars) debe producir una ruta
    saneada sin lanzar una excepción no controlada.
    """
    context = {"title": title, "uploader": uploader, "ext": ext or "mp4"}
    result = render_filename_template("{uploader}/{title}.{ext}", context)
    assert ".." not in result.split("/")
    for component in result.split("/"):
        assert not (_FORBIDDEN_CHARS & set(component))
