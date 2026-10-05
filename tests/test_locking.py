import threading
import time
from pathlib import Path

import pytest

from yt_cli.utils.locking import exclusive_lock


class TestExclusiveLock:
    def test_serializes_concurrent_read_modify_write(self, tmp_path: Path) -> None:
        """Reproduce exactamente la race condition documentada como B7 en
        AUDIT_REPORT.md: 20 hilos hacen leer->modificar->escribir sobre el
        mismo archivo. Sin lock, el valor final es << 20 (escrituras
        perdidas). Con el lock, debe ser exactamente 20.
        """
        target = tmp_path / "counter.txt"
        target.write_text("0")

        def worker() -> None:
            with exclusive_lock(target):
                current = int(target.read_text())
                time.sleep(0.005)  # fuerza la ventana de carrera
                target.write_text(str(current + 1))

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert int(target.read_text()) == 20

    def test_lock_is_reentrant_safe_sequentially(self, tmp_path: Path) -> None:
        target = tmp_path / "data.txt"
        with exclusive_lock(target):
            target.write_text("first")
        with exclusive_lock(target):
            target.write_text("second")
        assert target.read_text() == "second"

    def test_creates_lock_file_alongside_target(self, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "data.json"
        with exclusive_lock(target):
            pass
        assert (tmp_path / "sub" / "data.json.lock").exists()

    def test_raises_timeout_if_lock_held_by_another_thread(self, tmp_path: Path) -> None:
        target = tmp_path / "data.txt"
        released = threading.Event()

        def holder() -> None:
            with exclusive_lock(target):
                released.wait(timeout=2)

        t = threading.Thread(target=holder)
        t.start()
        time.sleep(0.05)  # asegura que 'holder' ya tomó el lock

        try:
            with pytest.raises(TimeoutError):
                with exclusive_lock(target, timeout_seconds=0.2):
                    pass
        finally:
            released.set()
            t.join()
