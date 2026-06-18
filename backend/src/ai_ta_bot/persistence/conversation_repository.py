"""Persistent per-user conversation history."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .database import connect, resolve_database_path


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConversationRepository:
    """Store history by group and sender to prevent cross-user context leaks."""

    def __init__(self, db_path: str | Path):
        self.db_path = resolve_database_path(db_path)
        self._initialize()

    def _initialize(self) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_name TEXT NOT NULL,
                    sender_key TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_user "
                "ON conversations(group_name, sender_key, id DESC)"
            )

    def append(
        self,
        group_name: str,
        sender_key: str,
        role: str,
        content: str,
    ) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError(f"unsupported conversation role: {role}")
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO conversations (
                    group_name, sender_key, role, content, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    group_name.strip(),
                    sender_key.strip() or "unknown",
                    role,
                    content.strip(),
                    _utcnow(),
                ),
            )

    def recent(
        self,
        group_name: str,
        sender_key: str,
        limit: int = 6,
    ) -> list[dict[str, str]]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM conversations
                WHERE group_name = ? AND sender_key = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (group_name.strip(), sender_key.strip() or "unknown", limit),
            ).fetchall()
        return [
            {"role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]

    def trim(self, group_name: str, sender_key: str, keep: int = 20) -> int:
        with connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                DELETE FROM conversations
                WHERE group_name = ? AND sender_key = ?
                  AND id NOT IN (
                    SELECT id FROM conversations
                    WHERE group_name = ? AND sender_key = ?
                    ORDER BY id DESC
                    LIMIT ?
                  )
                """,
                (
                    group_name.strip(),
                    sender_key.strip() or "unknown",
                    group_name.strip(),
                    sender_key.strip() or "unknown",
                    keep,
                ),
            )
        return cursor.rowcount
