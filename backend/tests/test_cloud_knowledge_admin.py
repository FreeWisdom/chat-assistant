import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from ai_ta_bot import config
from ai_ta_bot.knowledge.cloud_knowledge_admin import (
    AliyunBailianKnowledgeManager,
)


class Request:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeModels:
    ApplyFileUploadLeaseRequest = Request
    AddFileRequest = Request
    DescribeFileRequest = Request
    CreateIndexRequest = Request
    SubmitIndexJobRequest = Request
    SubmitIndexAddDocumentsJobRequest = Request
    GetIndexJobStatusRequest = Request
    DeleteIndexDocumentRequest = Request
    DeleteFileRequest = Request


def response(data, success=True):
    return SimpleNamespace(
        body=SimpleNamespace(
            success=success,
            code="Success",
            message="",
            data=data,
        )
    )


class FakeHttpResponse:
    def raise_for_status(self):
        return None


class FakeHttp:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeHttpResponse()


class FailingHttp:
    def request(self, method, url, **kwargs):
        raise requests.ConnectionError("network unavailable")


class FakeClient:
    def __init__(self):
        self.calls = []
        self.describe_statuses = ["PARSING", "PARSE_SUCCESS"]

    def apply_file_upload_lease_with_options(
        self,
        category_id,
        workspace_id,
        request,
        headers,
        runtime,
    ):
        self.calls.append(("lease", category_id, workspace_id, request))
        return response(SimpleNamespace(
            file_upload_lease_id="lease-1",
            param=SimpleNamespace(
                method="PUT",
                url="https://upload.example/file",
                headers='{"Content-Type":"text/plain","X-Test":"1"}',
            ),
        ))

    def add_file_with_options(
        self,
        workspace_id,
        request,
        headers,
        runtime,
    ):
        self.calls.append(("add_file", workspace_id, request))
        return response(SimpleNamespace(file_id="file-1"))

    def describe_file_with_options(
        self,
        workspace_id,
        file_id,
        request,
        headers,
        runtime,
    ):
        status = self.describe_statuses.pop(0)
        self.calls.append(("describe_file", workspace_id, file_id, status))
        return response(SimpleNamespace(status=status))

    def create_index_with_options(
        self,
        workspace_id,
        request,
        headers,
        runtime,
    ):
        self.calls.append(("create_index", workspace_id, request))
        return response(SimpleNamespace(id="index-1"))

    def submit_index_job_with_options(
        self,
        workspace_id,
        request,
        headers,
        runtime,
    ):
        self.calls.append(("submit_create", workspace_id, request))
        return response(SimpleNamespace(id="job-create-1"))

    def submit_index_add_documents_job_with_options(
        self,
        workspace_id,
        request,
        headers,
        runtime,
    ):
        self.calls.append(("submit_append", workspace_id, request))
        return response(SimpleNamespace(id="job-append-1"))

    def get_index_job_status_with_options(
        self,
        workspace_id,
        request,
        headers,
        runtime,
    ):
        self.calls.append(("job_status", workspace_id, request))
        return response(SimpleNamespace(
            status="COMPLETED",
            documents=[
                SimpleNamespace(
                    doc_id="file-1",
                    doc_name="资料.txt",
                    status="FINISH",
                    message="",
                )
            ],
        ))

    def delete_index_document_with_options(
        self,
        workspace_id,
        request,
        headers,
        runtime,
    ):
        self.calls.append(("delete_index_document", workspace_id, request))
        return response(SimpleNamespace(
            deleted_document=request.document_ids,
        ))

    def delete_file_with_options(
        self,
        file_id,
        workspace_id,
        request,
        headers,
        runtime,
    ):
        self.calls.append(("delete_file", workspace_id, file_id))
        return response(SimpleNamespace(file_id=file_id))


def upload(name="资料.txt", content=b"hello knowledge"):
    return SimpleNamespace(filename=name, file=io.BytesIO(content))


class CloudKnowledgeAdminTests(unittest.TestCase):
    def make_manager(self):
        client = FakeClient()
        http = FakeHttp()
        manager = AliyunBailianKnowledgeManager(
            client=client,
            models_module=FakeModels,
            runtime_factory=lambda: "runtime",
            http_session=http,
            sleep=lambda _: None,
        )
        return manager, client, http

    def test_uploads_file_creates_index_and_submits_job(self):
        manager, client, http = self.make_manager()

        result = manager.provision(
            workspace_id="workspace-1",
            name="测试知识库",
            description="测试描述",
            uploads=[upload()],
            tags=["测试"],
        )

        self.assertEqual(result.index_id, "index-1")
        self.assertEqual(result.job_id, "job-create-1")
        self.assertEqual(result.mode, "create")
        self.assertEqual(result.document_ids, ["file-1"])
        self.assertEqual(result.documents[0].file_name, "资料.txt")
        self.assertEqual(result.documents[0].size_bytes, 15)
        self.assertEqual(http.calls[0][0], "PUT")
        self.assertEqual(
            http.calls[0][2]["headers"]["Content-Type"],
            "text/plain",
        )

        lease_request = next(
            item[3] for item in client.calls if item[0] == "lease"
        )
        self.assertEqual(lease_request.category_type, "UNSTRUCTURED")
        self.assertEqual(lease_request.file_name, "资料.txt")
        self.assertEqual(lease_request.size_in_bytes, "15")

        create_request = next(
            item[2] for item in client.calls if item[0] == "create_index"
        )
        self.assertEqual(create_request.sink_type, "BUILT_IN")
        self.assertEqual(create_request.source_type, "DATA_CENTER_FILE")
        self.assertEqual(create_request.document_ids, ["file-1"])

    def test_existing_index_uses_append_job(self):
        manager, client, _ = self.make_manager()

        result = manager.provision(
            workspace_id="workspace-1",
            name="已有知识库",
            description="",
            uploads=[upload()],
            tags=[],
            index_id="existing-index",
        )

        self.assertEqual(result.index_id, "existing-index")
        self.assertEqual(result.job_id, "job-append-1")
        self.assertEqual(result.mode, "append")
        self.assertFalse(
            any(item[0] == "create_index" for item in client.calls)
        )
        append_request = next(
            item[2] for item in client.calls if item[0] == "submit_append"
        )
        self.assertEqual(append_request.index_id, "existing-index")
        self.assertEqual(append_request.document_ids, ["file-1"])

    def test_reads_index_job_status(self):
        manager, _, _ = self.make_manager()

        result = manager.get_job_status(
            workspace_id="workspace-1",
            index_id="index-1",
            job_id="job-1",
        )

        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.documents[0]["status"], "FINISH")

    def test_deletes_document_from_index_and_source(self):
        manager, client, _ = self.make_manager()

        source_cleaned = manager.delete_document(
            workspace_id="workspace-1",
            index_id="index-1",
            file_id="file-1",
        )

        self.assertTrue(source_cleaned)
        delete_request = next(
            item[2]
            for item in client.calls
            if item[0] == "delete_index_document"
        )
        self.assertEqual(delete_request.index_id, "index-1")
        self.assertEqual(delete_request.document_ids, ["file-1"])
        self.assertIn(
            ("delete_file", "workspace-1", "file-1"),
            client.calls,
        )

    def test_waits_while_file_is_in_parse_queue(self):
        manager, client, _ = self.make_manager()
        client.describe_statuses = ["IN_PARSE_QUEUE", "PARSE_SUCCESS"]

        result = manager.provision(
            workspace_id="workspace-1",
            name="测试知识库",
            description="",
            uploads=[upload()],
            tags=[],
        )

        self.assertEqual(result.document_ids, ["file-1"])

    def test_rejects_unsupported_and_oversized_files(self):
        manager, _, _ = self.make_manager()
        with self.assertRaisesRegex(ValueError, "不支持"):
            manager.provision(
                workspace_id="workspace-1",
                name="测试",
                description="",
                uploads=[upload("恶意.exe")],
                tags=[],
            )

        with patch.object(config, "KNOWLEDGE_UPLOAD_MAX_FILE_BYTES", 3):
            with self.assertRaisesRegex(ValueError, "超过大小限制"):
                manager.provision(
                    workspace_id="workspace-1",
                    name="测试",
                    description="",
                    uploads=[upload(content=b"1234")],
                    tags=[],
                )

    def test_reports_binary_upload_network_failure(self):
        manager = AliyunBailianKnowledgeManager(
            client=FakeClient(),
            models_module=FakeModels,
            runtime_factory=lambda: "runtime",
            http_session=FailingHttp(),
            sleep=lambda _: None,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "上传文件到百炼临时存储失败",
        ):
            manager.provision(
                workspace_id="workspace-1",
                name="测试",
                description="",
                uploads=[upload()],
                tags=[],
            )


if __name__ == "__main__":
    unittest.main()
