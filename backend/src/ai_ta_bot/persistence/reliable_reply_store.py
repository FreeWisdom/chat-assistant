"""wxauto4-compatible reply store with deterministic connection closing."""

from __future__ import annotations

import sqlite3

from wxauto4.reply_queue import ReplyTaskStore


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class ReliableReplyTaskStore(ReplyTaskStore):
    """Fix sqlite3 context-manager handles left open by upstream store."""

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=10,
            factory=_ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection
