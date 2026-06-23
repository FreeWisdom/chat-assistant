"""Cross-process lock preventing duplicate desktop bot instances."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .database import resolve_database_path


@contextmanager
def single_instance_lock(path: str | Path) -> Iterator[Path]:
    lock_path = resolve_database_path(path)
    handle = lock_path.open("a+b")
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)

        try:
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("已有机器人进程正在运行，拒绝重复启动") from exc

        yield lock_path
    finally:
        try:
            handle.seek(0)
            try:
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except ImportError:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()
