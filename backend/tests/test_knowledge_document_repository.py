import tempfile
import unittest
from pathlib import Path

from ai_ta_bot.persistence import KnowledgeDocumentRepository


class KnowledgeDocumentRepositoryTests(unittest.TestCase):
    def make_repository(self):
        directory = tempfile.TemporaryDirectory()
        repository = KnowledgeDocumentRepository(
            Path(directory.name) / "state.db"
        )
        self.addCleanup(directory.cleanup)
        return repository

    def test_tracks_initial_document_and_activation(self):
        repository = self.make_repository()
        pending = repository.create_pending(
            knowledge_base_id="kb-1",
            file_name="制度.pdf",
            size_bytes=100,
            checksum="md5-v1",
            cloud_file_id="file-v1",
            cloud_job_id="job-v1",
        )

        self.assertEqual(pending["status"], "PROCESSING")
        self.assertIsNone(pending["currentVersion"])

        active = repository.activate_version(pending["id"], 1)
        self.assertEqual(active["status"], "ACTIVE")
        self.assertEqual(active["currentVersion"], 1)
        self.assertEqual(active["versions"][0]["status"], "ACTIVE")
        self.assertEqual(
            repository.active_cloud_file_ids("kb-1"),
            ["file-v1"],
        )

    def test_replacement_keeps_old_version_until_activation(self):
        repository = self.make_repository()
        created = repository.create_pending(
            knowledge_base_id="kb-1",
            file_name="制度.pdf",
            size_bytes=100,
            checksum="md5-v1",
            cloud_file_id="file-v1",
            cloud_job_id="job-v1",
        )
        repository.activate_version(created["id"], 1)

        updating = repository.start_replacement(
            created["id"],
            file_name="制度-新版.pdf",
            size_bytes=120,
            checksum="md5-v2",
            cloud_file_id="file-v2",
            cloud_job_id="job-v2",
        )

        self.assertEqual(updating["status"], "UPDATING")
        self.assertEqual(updating["currentVersion"], 1)
        self.assertEqual(
            repository.active_cloud_file_ids("kb-1"),
            ["file-v1"],
        )

        active = repository.activate_version(created["id"], 2)
        statuses = {
            item["version"]: item["status"]
            for item in active["versions"]
        }
        self.assertEqual(active["currentVersion"], 2)
        self.assertEqual(statuses, {2: "ACTIVE", 1: "SUPERSEDED"})
        self.assertEqual(
            repository.active_cloud_file_ids("kb-1"),
            ["file-v2"],
        )

    def test_failed_replacement_keeps_current_version_active(self):
        repository = self.make_repository()
        created = repository.create_pending(
            knowledge_base_id="kb-1",
            file_name="制度.pdf",
            size_bytes=100,
            checksum="md5-v1",
            cloud_file_id="file-v1",
            cloud_job_id="job-v1",
        )
        repository.activate_version(created["id"], 1)
        repository.start_replacement(
            created["id"],
            file_name="制度-新版.pdf",
            size_bytes=120,
            checksum="md5-v2",
            cloud_file_id="file-v2",
            cloud_job_id="job-v2",
        )

        failed = repository.fail_version(
            created["id"],
            2,
            "解析失败",
        )

        self.assertEqual(failed["status"], "ACTIVE")
        self.assertEqual(failed["currentVersion"], 1)
        self.assertEqual(
            repository.active_cloud_file_ids("kb-1"),
            ["file-v1"],
        )

    def test_soft_delete_preserves_version_history(self):
        repository = self.make_repository()
        created = repository.create_pending(
            knowledge_base_id="kb-1",
            file_name="制度.pdf",
            size_bytes=100,
            checksum="md5-v1",
            cloud_file_id="file-v1",
            cloud_job_id="job-v1",
        )
        repository.activate_version(created["id"], 1)

        deleted = repository.mark_deleted(created["id"])

        self.assertEqual(deleted["status"], "DELETED")
        self.assertEqual(deleted["versions"][0]["status"], "DELETED")
        self.assertEqual(repository.active_cloud_file_ids("kb-1"), [])
        self.assertEqual(len(repository.list("kb-1")), 1)


if __name__ == "__main__":
    unittest.main()
