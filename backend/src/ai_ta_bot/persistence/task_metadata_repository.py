"""Project-owned metadata for wxauto4 reply tasks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .database import connect


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TaskMetadataRepository:
    """Store context and delivery phases without changing wxauto4's schema."""

    def __init__(self, db_path: str | Path):
        self.db_path = db_path
        with connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reply_task_metadata (
                    task_id INTEGER PRIMARY KEY,
                    trigger_type TEXT,
                    quote_nickname TEXT,
                    quote_content TEXT,
                    phase TEXT NOT NULL DEFAULT 'pending',
                    generated_answer TEXT,
                    send_mode TEXT,
                    next_retry_at TEXT,
                    last_error TEXT,
                    verified_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_reply_task_metadata_retry "
                "ON reply_task_metadata(phase, next_retry_at)"
            )

    def save_context(
        self,
        task_id: int,
        *,
        trigger_type: str,
        quote_nickname: str = "",
        quote_content: str = "",
    ) -> None:
        now = _utcnow()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO reply_task_metadata (
                    task_id, trigger_type, quote_nickname, quote_content,
                    phase, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    trigger_type = excluded.trigger_type,
                    quote_nickname = CASE
                        WHEN excluded.quote_nickname <> ''
                        THEN excluded.quote_nickname
                        ELSE reply_task_metadata.quote_nickname
                    END,
                    quote_content = CASE
                        WHEN excluded.quote_content <> ''
                        THEN excluded.quote_content
                        ELSE reply_task_metadata.quote_content
                    END,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    trigger_type,
                    quote_nickname,
                    quote_content,
                    now,
                    now,
                ),
            )

    def ensure(self, task_id: int) -> None:
        now = _utcnow()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO reply_task_metadata (
                    task_id, phase, created_at, updated_at
                ) VALUES (?, 'pending', ?, ?)
                """,
                (task_id, now, now),
            )

    def get(self, task_id: int) -> dict:
        self.ensure(task_id)
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM reply_task_metadata WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return dict(row) if row else {}

    def set_phase(
        self,
        task_id: int,
        phase: str,
        *,
        generated_answer: str | None = None,
        send_mode: str | None = None,
        next_retry_at: str | None = None,
        last_error: str | None = None,
        verified: bool = False,
    ) -> None:
        self.ensure(task_id)
        now = _utcnow()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE reply_task_metadata
                SET phase = ?,
                    generated_answer = COALESCE(?, generated_answer),
                    send_mode = COALESCE(?, send_mode),
                    next_retry_at = ?,
                    last_error = ?,
                    verified_at = CASE WHEN ? THEN ? ELSE verified_at END,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    phase,
                    generated_answer,
                    send_mode,
                    next_retry_at,
                    last_error,
                    int(verified),
                    now,
                    now,
                    task_id,
                ),
            )

    def schedule_retry(
        self,
        task_id: int,
        *,
        attempts: int,
        error: str,
        max_attempts: int,
        base_seconds: float,
        max_seconds: float,
    ) -> str:
        if attempts >= max_attempts:
            self.set_phase(
                task_id,
                "dead_letter",
                last_error=error,
            )
            return "dead_letter"

        delay = min(
            max_seconds,
            base_seconds * (2 ** max(0, attempts - 1)),
        )
        retry_at = (
            datetime.now(timezone.utc) + timedelta(seconds=delay)
        ).isoformat(timespec="milliseconds")
        self.set_phase(
            task_id,
            "retry_wait",
            next_retry_at=retry_at,
            last_error=error,
        )
        return "retry_wait"

    def retry_due(self, task_id: int, now: datetime | None = None) -> bool:
        metadata = self.get(task_id)
        if metadata.get("phase") == "dead_letter":
            return False
        value = metadata.get("next_retry_at")
        if not value:
            return True
        try:
            retry_at = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return True
        current = now or datetime.now(timezone.utc)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return current >= retry_at
