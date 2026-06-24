import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_ta_bot import config
from ai_ta_bot.admin_app import app
from ai_ta_bot.knowledge.cloud_knowledge_admin import (
    IndexJobStatus,
    ProvisionResult,
    UploadedDocument,
)
from ai_ta_bot.persistence import KnowledgeDocumentRepository


class AdminAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.sync_headers = (
            {"X-Admin-Token": config.ADMIN_SYNC_TOKEN}
            if config.ADMIN_SYNC_TOKEN
            else {}
        )

    def test_read_endpoints_are_available(self):
        for path in (
            "/api/config",
            "/api/backups",
            "/api/runtime/health",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)

        response = self.client.get(
            "/api/sync/health",
            headers=self.sync_headers,
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_validate_endpoint_accepts_current_config(self):
        current = self.client.get("/api/config").json()["config"]
        response = self.client.post("/api/validate", json=current)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["errors"], [])

    def test_browser_config_hides_cloud_vendor_details(self):
        payload = self.client.get("/api/config").json()["config"]
        for knowledge_base in payload["knowledgeBases"]:
            self.assertNotIn("provider", knowledge_base)
            self.assertNotIn("workspaceId", knowledge_base)
            self.assertNotIn("indexId", knowledge_base)
            self.assertNotIn("indexJobId", knowledge_base)
            self.assertNotIn("documentIds", knowledge_base)
            self.assertIn("configured", knowledge_base)
            self.assertIn("documentCount", knowledge_base)

    def test_local_knowledge_upload_api_is_removed(self):
        response = self.client.get("/api/knowledge/files")
        self.assertEqual(response.status_code, 404)

    def test_cloud_knowledge_provision_endpoint_updates_config(self):
        manager = SimpleNamespace(
            provision=lambda **kwargs: ProvisionResult(
                index_id="index-new",
                job_id="job-new",
                job_status="PENDING",
                documents=[UploadedDocument(
                    file_id="file-new",
                    file_name="资料.txt",
                    size_bytes=5,
                    checksum="md5-new",
                )],
                mode="create",
            )
        )
        saved = {
            "knowledgeBases": [{
                "id": "new-kb",
                "name": "新知识库",
                "provider": "aliyun_bailian",
                "workspaceId": "workspace-1",
                "indexId": "index-new",
                "indexJobId": "job-new",
                "indexStatus": "PENDING",
                "documentIds": ["file-new"],
            }],
            "botProfiles": [],
            "styles": [],
            "bindings": [],
            "global": {},
        }
        draft = {
            "id": "new-kb",
            "name": "新知识库",
            "tags": ["资料"],
        }

        with tempfile.TemporaryDirectory() as directory:
            repository = KnowledgeDocumentRepository(
                Path(directory) / "state.db"
            )
            with (
                patch(
                    "ai_ta_bot.admin.routers.knowledge._manager_factory",
                    return_value=manager,
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge._repository_factory",
                    return_value=repository,
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge.config_store.read_config",
                    return_value={
                        "knowledgeBases": [],
                        "botProfiles": [],
                        "styles": [],
                        "bindings": [],
                        "global": {},
                    },
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge.config_store.upsert_knowledge_base",
                    return_value=saved,
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge.config.ALIYUN_BAILIAN_WORKSPACE_ID",
                    "workspace-1",
                ),
            ):
                response = self.client.post(
                    "/api/knowledge/provision",
                    data={"knowledge_base": json.dumps(draft)},
                    files=[
                        ("files", ("资料.txt", b"hello", "text/plain")),
                    ],
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["mode"], "create")
        self.assertTrue(payload["knowledgeBase"]["configured"])
        self.assertEqual(payload["knowledgeBase"]["documentCount"], 1)
        self.assertNotIn("workspaceId", payload["knowledgeBase"])
        self.assertNotIn("indexId", payload["knowledgeBase"])
        self.assertNotIn("indexJobId", payload["knowledgeBase"])
        self.assertNotIn("documentIds", payload["knowledgeBase"])

    def test_cloud_knowledge_job_endpoint_returns_status(self):
        manager = SimpleNamespace(
            get_job_status=lambda **kwargs: IndexJobStatus(
                status="COMPLETED",
                documents=[{
                    "id": "file-1",
                    "name": "资料.txt",
                    "status": "FINISH",
                    "message": "",
                }],
            )
        )
        current = {
            "knowledgeBases": [{
                "id": "kb-1",
                "name": "测试知识库",
                "provider": "aliyun_bailian",
                "workspaceId": "workspace-1",
                "indexId": "index-1",
                "indexJobId": "job-1",
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            repository = KnowledgeDocumentRepository(
                Path(directory) / "state.db"
            )
            with (
                patch(
                    "ai_ta_bot.admin.routers.knowledge._manager_factory",
                    return_value=manager,
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge._repository_factory",
                    return_value=repository,
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge.config_store.read_config",
                    return_value=current,
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge.config_store.update_knowledge_cloud_state",
                    return_value=current,
                ),
            ):
                response = self.client.get("/api/knowledge/kb-1/job")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "COMPLETED")
        self.assertNotIn("id", response.json()["documents"][0])
        self.assertNotIn(
            "workspaceId",
            response.json()["config"]["knowledgeBases"][0],
        )

    def test_document_list_replace_finalize_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = KnowledgeDocumentRepository(
                Path(directory) / "state.db"
            )
            created = repository.create_pending(
                knowledge_base_id="kb-1",
                file_name="制度.pdf",
                size_bytes=100,
                checksum="md5-v1",
                cloud_file_id="file-v1",
                cloud_job_id="job-v1",
            )
            repository.activate_version(created["id"], 1)

            current = {
                "knowledgeBases": [{
                    "id": "kb-1",
                    "name": "测试知识库",
                    "description": "测试资料",
                    "provider": "aliyun_bailian",
                    "workspaceId": "workspace-1",
                    "indexId": "index-1",
                    "indexJobId": "job-v1",
                    "indexStatus": "COMPLETED",
                    "documentIds": ["file-v1"],
                    "tags": [],
                }],
                "botProfiles": [],
                "styles": [],
                "bindings": [],
                "global": {},
            }
            deleted_files = []

            def update_state(kb_id, **values):
                item = current["knowledgeBases"][0]
                if values.get("index_job_id") is not None:
                    item["indexJobId"] = values["index_job_id"]
                if values.get("index_status") is not None:
                    item["indexStatus"] = values["index_status"]
                if values.get("document_ids") is not None:
                    item["documentIds"] = values["document_ids"]
                return current

            manager = SimpleNamespace(
                provision=lambda **kwargs: ProvisionResult(
                    index_id="index-1",
                    job_id="job-v2",
                    job_status="PENDING",
                    documents=[UploadedDocument(
                        file_id="file-v2",
                        file_name="制度-新版.pdf",
                        size_bytes=120,
                        checksum="md5-v2",
                    )],
                    mode="append",
                ),
                get_job_status=lambda **kwargs: IndexJobStatus(
                    status="COMPLETED",
                    documents=[{
                        "id": "file-v2",
                        "name": "制度-新版.pdf",
                        "status": "FINISH",
                        "message": "",
                    }],
                ),
                delete_document=lambda **kwargs: (
                    deleted_files.append(kwargs["file_id"]) or True
                ),
            )

            with (
                patch(
                    "ai_ta_bot.admin.routers.knowledge._manager_factory",
                    return_value=manager,
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge._repository_factory",
                    return_value=repository,
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge.config_store.read_config",
                    return_value=current,
                ),
                patch(
                    "ai_ta_bot.admin.routers.knowledge.config_store.update_knowledge_cloud_state",
                    side_effect=update_state,
                ),
            ):
                listed = self.client.get(
                    "/api/knowledge/kb-1/documents"
                )
                self.assertEqual(listed.status_code, 200, listed.text)
                listed_document = listed.json()["documents"][0]
                self.assertNotIn(
                    "cloudFileId",
                    json.dumps(listed_document),
                )

                replaced = self.client.post(
                    f"/api/knowledge/kb-1/documents/{created['id']}/replace",
                    files=[
                        (
                            "file",
                            ("制度-新版.pdf", b"new document", "application/pdf"),
                        )
                    ],
                )
                self.assertEqual(replaced.status_code, 200, replaced.text)
                self.assertEqual(
                    replaced.json()["document"]["status"],
                    "UPDATING",
                )

                completed = self.client.get("/api/knowledge/kb-1/job")
                self.assertEqual(completed.status_code, 200, completed.text)
                activated = repository.get(created["id"])
                self.assertEqual(activated["currentVersion"], 2)
                self.assertEqual(deleted_files, ["file-v1"])

                deleted = self.client.delete(
                    f"/api/knowledge/kb-1/documents/{created['id']}"
                )
                self.assertEqual(deleted.status_code, 200, deleted.text)
                self.assertEqual(
                    deleted.json()["document"]["status"],
                    "DELETED",
                )
                self.assertEqual(deleted_files, ["file-v1", "file-v2"])


if __name__ == "__main__":
    unittest.main()
