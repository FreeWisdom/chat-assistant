"""Persistent knowledge-document and version metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .database import connect, resolve_database_path


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class KnowledgeDocumentRepository:
    """Track logical documents while cloud file IDs remain server-only."""

    def __init__(self, db_path: str | Path):
        self.db_path = resolve_database_path(db_path)
        self._initialize()

    def _initialize(self) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY,
                    knowledge_base_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_version INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_document_versions (
                    document_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    cloud_file_id TEXT NOT NULL,
                    cloud_job_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    replaces_version INTEGER,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    activated_at TEXT,
                    deleted_at TEXT,
                    PRIMARY KEY (document_id, version),
                    FOREIGN KEY (document_id)
                        REFERENCES knowledge_documents(id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_documents_kb "
                "ON knowledge_documents(knowledge_base_id, updated_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_versions_job "
                "ON knowledge_document_versions(cloud_job_id, status)"
            )

    def create_pending(
        self,
        *,
        knowledge_base_id: str,
        file_name: str,
        size_bytes: int,
        checksum: str,
        cloud_file_id: str,
        cloud_job_id: str,
    ) -> dict:
        document_id = uuid4().hex
        now = _utcnow()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO knowledge_documents (
                    id, knowledge_base_id, name, status,
                    current_version, created_at, updated_at
                ) VALUES (?, ?, ?, 'PROCESSING', NULL, ?, ?)
                """,
                (
                    document_id,
                    knowledge_base_id,
                    file_name,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO knowledge_document_versions (
                    document_id, version, file_name, size_bytes,
                    checksum, cloud_file_id, cloud_job_id,
                    status, created_at
                ) VALUES (?, 1, ?, ?, ?, ?, ?, 'PROCESSING', ?)
                """,
                (
                    document_id,
                    file_name,
                    int(size_bytes),
                    checksum,
                    cloud_file_id,
                    cloud_job_id,
                    now,
                ),
            )
        return self.get(document_id)

    def start_replacement(
        self,
        document_id: str,
        *,
        file_name: str,
        size_bytes: int,
        checksum: str,
        cloud_file_id: str,
        cloud_job_id: str,
    ) -> dict:
        current = self.get(document_id, include_internal=True)
        if not current:
            raise ValueError("文档不存在")
        if current["status"] in {"PROCESSING", "UPDATING", "DELETING"}:
            raise ValueError("文档正在处理中，请稍后再试")
        if current["status"] == "DELETED":
            raise ValueError("已删除的文档不能替换")
        current_version = current.get("currentVersion")
        if not current_version:
            raise ValueError("文档尚无可替换的有效版本")

        version = max(
            (item["version"] for item in current["versions"]),
            default=0,
        ) + 1
        now = _utcnow()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO knowledge_document_versions (
                    document_id, version, file_name, size_bytes,
                    checksum, cloud_file_id, cloud_job_id, status,
                    replaces_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PROCESSING', ?, ?)
                """,
                (
                    document_id,
                    version,
                    file_name,
                    int(size_bytes),
                    checksum,
                    cloud_file_id,
                    cloud_job_id,
                    current_version,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE knowledge_documents
                SET status = 'UPDATING', updated_at = ?, deleted_at = NULL
                WHERE id = ?
                """,
                (now, document_id),
            )
        return self.get(document_id)

    def pending_versions_for_job(self, cloud_job_id: str) -> list[dict]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT v.*, d.knowledge_base_id, d.current_version
                FROM knowledge_document_versions v
                JOIN knowledge_documents d ON d.id = v.document_id
                WHERE v.cloud_job_id = ? AND v.status = 'PROCESSING'
                ORDER BY v.document_id, v.version
                """,
                (cloud_job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def activate_version(
        self,
        document_id: str,
        version: int,
    ) -> dict:
        now = _utcnow()
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT replaces_version
                FROM knowledge_document_versions
                WHERE document_id = ? AND version = ?
                """,
                (document_id, version),
            ).fetchone()
            if row is None:
                raise ValueError("文档版本不存在")
            replaces_version = row["replaces_version"]
            if replaces_version:
                connection.execute(
                    """
                    UPDATE knowledge_document_versions
                    SET status = 'SUPERSEDED', deleted_at = ?
                    WHERE document_id = ? AND version = ?
                    """,
                    (now, document_id, replaces_version),
                )
            connection.execute(
                """
                UPDATE knowledge_document_versions
                SET status = 'ACTIVE', activated_at = ?, error = NULL
                WHERE document_id = ? AND version = ?
                """,
                (now, document_id, version),
            )
            connection.execute(
                """
                UPDATE knowledge_documents
                SET name = (
                        SELECT file_name
                        FROM knowledge_document_versions
                        WHERE document_id = ? AND version = ?
                    ),
                    status = 'ACTIVE',
                    current_version = ?,
                    updated_at = ?,
                    deleted_at = NULL
                WHERE id = ?
                """,
                (
                    document_id,
                    version,
                    version,
                    now,
                    document_id,
                ),
            )
        return self.get(document_id)

    def fail_job(
        self,
        cloud_job_id: str,
        error: str,
    ) -> None:
        now = _utcnow()
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT document_id, version, replaces_version
                FROM knowledge_document_versions
                WHERE cloud_job_id = ? AND status = 'PROCESSING'
                """,
                (cloud_job_id,),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    UPDATE knowledge_document_versions
                    SET status = 'FAILED', error = ?
                    WHERE document_id = ? AND version = ?
                    """,
                    (error, row["document_id"], row["version"]),
                )
                if row["replaces_version"]:
                    document_status = "ACTIVE"
                else:
                    document_status = "FAILED"
                connection.execute(
                    """
                    UPDATE knowledge_documents
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (document_status, now, row["document_id"]),
                )

    def fail_version(
        self,
        document_id: str,
        version: int,
        error: str,
    ) -> dict:
        now = _utcnow()
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT replaces_version
                FROM knowledge_document_versions
                WHERE document_id = ? AND version = ?
                """,
                (document_id, version),
            ).fetchone()
            if row is None:
                raise ValueError("文档版本不存在")
            connection.execute(
                """
                UPDATE knowledge_document_versions
                SET status = 'FAILED', error = ?
                WHERE document_id = ? AND version = ?
                """,
                (error, document_id, version),
            )
            connection.execute(
                """
                UPDATE knowledge_documents
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    "ACTIVE" if row["replaces_version"] else "FAILED",
                    now,
                    document_id,
                ),
            )
        return self.get(document_id)

    def mark_deleted(self, document_id: str) -> dict:
        current = self.get(document_id, include_internal=True)
        if not current:
            raise ValueError("文档不存在")
        if current["status"] in {"PROCESSING", "UPDATING", "DELETING"}:
            raise ValueError("文档正在处理中，请稍后再试")
        if current["status"] == "DELETED":
            return self.get(document_id)

        now = _utcnow()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE knowledge_documents
                SET status = 'DELETED', updated_at = ?, deleted_at = ?
                WHERE id = ?
                """,
                (now, now, document_id),
            )
            if current.get("currentVersion"):
                connection.execute(
                    """
                    UPDATE knowledge_document_versions
                    SET status = 'DELETED', deleted_at = ?
                    WHERE document_id = ? AND version = ?
                    """,
                    (now, document_id, current["currentVersion"]),
                )
            else:
                connection.execute(
                    """
                    UPDATE knowledge_document_versions
                    SET status = 'DELETED', deleted_at = ?
                    WHERE document_id = ? AND version = (
                        SELECT MAX(version)
                        FROM knowledge_document_versions
                        WHERE document_id = ?
                    )
                    """,
                    (now, document_id, document_id),
                )
        return self.get(document_id)

    def list(self, knowledge_base_id: str) -> list[dict]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT id
                FROM knowledge_documents
                WHERE knowledge_base_id = ?
                ORDER BY deleted_at IS NOT NULL, updated_at DESC
                """,
                (knowledge_base_id,),
            ).fetchall()
        return [
            self.get(row["id"])
            for row in rows
        ]

    def get(
        self,
        document_id: str,
        *,
        include_internal: bool = False,
    ) -> dict:
        with connect(self.db_path) as connection:
            document = connection.execute(
                "SELECT * FROM knowledge_documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if document is None:
                return {}
            versions = connection.execute(
                """
                SELECT *
                FROM knowledge_document_versions
                WHERE document_id = ?
                ORDER BY version DESC
                """,
                (document_id,),
            ).fetchall()

        result = {
            "id": document["id"],
            "knowledgeBaseId": document["knowledge_base_id"],
            "name": document["name"],
            "status": document["status"],
            "currentVersion": document["current_version"],
            "createdAt": document["created_at"],
            "updatedAt": document["updated_at"],
            "deletedAt": document["deleted_at"],
            "versions": [],
        }
        for row in versions:
            item = {
                "version": row["version"],
                "fileName": row["file_name"],
                "sizeBytes": row["size_bytes"],
                "checksum": row["checksum"],
                "status": row["status"],
                "error": row["error"],
                "createdAt": row["created_at"],
                "activatedAt": row["activated_at"],
                "deletedAt": row["deleted_at"],
            }
            if include_internal:
                item.update({
                    "cloudFileId": row["cloud_file_id"],
                    "cloudJobId": row["cloud_job_id"],
                    "replacesVersion": row["replaces_version"],
                })
            result["versions"].append(item)
        return result

    def sync_from_cloud(
        self,
        knowledge_base_id: str,
        cloud_documents: list[dict],
    ) -> None:
        """Upsert local records from cloud document list."""
        now = _utcnow()
        with connect(self.db_path) as connection:
            for cloud in cloud_documents:
                cloud_file_id = cloud["id"]
                if not cloud_file_id:
                    continue

                existing = connection.execute(
                    """
                    SELECT d.id, d.current_version
                    FROM knowledge_documents d
                    JOIN knowledge_document_versions v
                      ON v.document_id = d.id
                     AND v.cloud_file_id = ?
                    WHERE d.knowledge_base_id = ?
                    ORDER BY v.version DESC
                    LIMIT 1
                    """,
                    (cloud_file_id, knowledge_base_id),
                ).fetchone()

                cloud_status = self._map_cloud_status(cloud.get("status", ""))

                if existing:
                    connection.execute(
                        """
                        UPDATE knowledge_documents
                        SET name = ?, status = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (cloud["name"], cloud_status, now, existing["id"]),
                    )
                    if existing["current_version"]:
                        connection.execute(
                            """
                            UPDATE knowledge_document_versions
                            SET status = ?, file_name = ?, size_bytes = ?
                            WHERE document_id = ? AND version = ?
                            """,
                            (
                                "ACTIVE" if cloud_status == "ACTIVE" else cloud_status,
                                cloud["name"],
                                int(cloud.get("size", 0) or 0),
                                existing["id"],
                                existing["current_version"],
                            ),
                        )
                else:
                    document_id = uuid4().hex
                    connection.execute(
                        """
                        INSERT INTO knowledge_documents (
                            id, knowledge_base_id, name, status,
                            current_version, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 1, ?, ?)
                        """,
                        (
                            document_id,
                            knowledge_base_id,
                            cloud["name"],
                            cloud_status,
                            now,
                            now,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO knowledge_document_versions (
                            document_id, version, file_name, size_bytes,
                            checksum, cloud_file_id, cloud_job_id,
                            status, created_at, activated_at
                        ) VALUES (?, 1, ?, ?, ?, ?, '', ?, ?, ?)
                        """,
                        (
                            document_id,
                            cloud["name"],
                            int(cloud.get("size", 0) or 0),
                            "",
                            cloud_file_id,
                            "ACTIVE" if cloud_status == "ACTIVE" else cloud_status,
                            now,
                            now if cloud_status == "ACTIVE" else None,
                        ),
                    )

    @staticmethod
    def _map_cloud_status(cloud_status: str) -> str:
        finished = {"FINISH", "PARSE_SUCCESS", "FILE_IS_READY", "INDEX_BUILD_SUCCESS"}
        processing = {"INIT", "IN_PARSE_QUEUE", "PARSING", "SAFE_CHECKING", "INDEX_BUILDING"}
        failed = {"PARSE_FAILED", "SAFE_CHECK_FAILED", "INDEX_BUILDING_FAILED", "FILE_EXPIRED"}
        status_upper = str(cloud_status or "").strip().upper()
        if status_upper in finished:
            return "ACTIVE"
        if status_upper in processing:
            return "PROCESSING"
        if status_upper in failed:
            return "FAILED"
        return status_upper or "UNKNOWN"

    def active_cloud_file_ids(self, knowledge_base_id: str) -> list[str]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT v.cloud_file_id
                FROM knowledge_documents d
                JOIN knowledge_document_versions v
                  ON v.document_id = d.id
                 AND v.version = d.current_version
                WHERE d.knowledge_base_id = ?
                  AND d.status <> 'DELETED'
                  AND v.status = 'ACTIVE'
                ORDER BY d.created_at
                """,
                (knowledge_base_id,),
            ).fetchall()
        return [row["cloud_file_id"] for row in rows]
