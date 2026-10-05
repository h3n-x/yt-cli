from pathlib import Path

from yt_cli.services.cache import MetadataCache


class TestMetadataCache:
    def test_returns_none_for_missing_key(self, tmp_path: Path) -> None:
        cache = MetadataCache(ttl_hours=1, base_dir=tmp_path)
        assert cache.get("https://youtu.be/missing") is None

    def test_set_and_get_roundtrip(self, tmp_path: Path) -> None:
        cache = MetadataCache(ttl_hours=1, base_dir=tmp_path)
        cache.set("https://youtu.be/abc", {"title": "Video"})
        assert cache.get("https://youtu.be/abc") == {"title": "Video"}

    def test_disabled_when_ttl_zero(self, tmp_path: Path) -> None:
        cache = MetadataCache(ttl_hours=0, base_dir=tmp_path)
        cache.set("https://youtu.be/abc", {"title": "Video"})
        assert cache.get("https://youtu.be/abc") is None

    def test_expired_entry_returns_none_and_is_removed(self, tmp_path: Path) -> None:
        cache = MetadataCache(ttl_hours=1, base_dir=tmp_path)
        cache.set("https://youtu.be/abc", {"title": "Video"})

        # Simula expiración reescribiendo el archivo con un timestamp antiguo.
        entry_files = list((tmp_path).glob("*.json"))
        assert len(entry_files) == 1
        import orjson

        payload = orjson.loads(entry_files[0].read_bytes())
        payload["cached_at"] = "2000-01-01T00:00:00+00:00"
        entry_files[0].write_bytes(orjson.dumps(payload))

        assert cache.get("https://youtu.be/abc") is None
        assert not entry_files[0].exists()

    def test_clear_removes_all_entries(self, tmp_path: Path) -> None:
        cache = MetadataCache(ttl_hours=1, base_dir=tmp_path)
        cache.set("https://youtu.be/a", {"title": "A"})
        cache.set("https://youtu.be/b", {"title": "B"})
        removed = cache.clear()
        assert removed == 2
        assert cache.stats().entry_count == 0

    def test_stats_reports_entry_count(self, tmp_path: Path) -> None:
        cache = MetadataCache(ttl_hours=1, base_dir=tmp_path)
        cache.set("https://youtu.be/a", {"title": "A"})
        stats = cache.stats()
        assert stats.entry_count == 1
        assert stats.total_bytes > 0
