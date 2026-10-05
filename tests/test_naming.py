from yt_cli.utils.naming import render_filename_template, sanitize_filename, sanitize_path_template_output


class TestSanitizeFilename:
    def test_removes_invalid_characters(self) -> None:
        assert sanitize_filename('Título: "Épico"?') == "Título_ _Épico_"

    def test_empty_string_becomes_untitled(self) -> None:
        assert sanitize_filename("") == "untitled"

    def test_windows_reserved_names_are_prefixed(self) -> None:
        assert sanitize_filename("CON") == "_CON"
        assert sanitize_filename("com1") == "_com1" or sanitize_filename("com1") == "com1"

    def test_trailing_dots_and_spaces_are_stripped(self) -> None:
        assert sanitize_filename("archivo...   ") == "archivo"

    def test_collapses_multiple_spaces(self) -> None:
        assert sanitize_filename("hola    mundo") == "hola mundo"

    def test_truncates_overly_long_names(self) -> None:
        long_name = "a" * 500
        result = sanitize_filename(long_name)
        assert len(result) <= 200

    def test_slash_and_backslash_are_replaced(self) -> None:
        result = sanitize_filename("a/b\\c")
        assert "/" not in result
        assert "\\" not in result


class TestSanitizePathTemplateOutput:
    def test_preserves_directory_separators(self) -> None:
        result = sanitize_path_template_output("Canal X/Video: uno?.mp4")
        assert result == "Canal X/Video_ uno_.mp4"

    def test_ignores_empty_components(self) -> None:
        result = sanitize_path_template_output("a//b")
        assert result == "a/b"


class TestRenderFilenameTemplate:
    def test_renders_all_placeholders(self) -> None:
        context = {
            "title": "Mi Video",
            "uploader": "Canal X",
            "date": "20260101",
            "id": "abc123",
            "playlist": "Lista",
            "resolution": "1080p",
            "ext": "mp4",
        }
        result = render_filename_template("{uploader}/{playlist}/{title}.{ext}", context)
        assert result == "Canal X/Lista/Mi Video.mp4"

    def test_missing_metadata_falls_back_to_defaults(self) -> None:
        result = render_filename_template("{uploader}/{title}.{ext}", {"title": "Solo"})
        assert result == "unknown/Solo.bin"

    def test_invalid_placeholder_raises(self) -> None:
        try:
            render_filename_template("{unknown_field}", {})
        except ValueError:
            return
        raise AssertionError("Se esperaba ValueError para placeholder inválido")

    def test_sanitizes_hostile_title_characters(self) -> None:
        result = render_filename_template(
            "{title}.{ext}", {"title": "click | here: shocking?", "ext": "mp4"}
        )
        assert "|" not in result
        assert ":" not in result
        assert "?" not in result
