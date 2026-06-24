"""Provision and update Alibaba Cloud Model Studio knowledge bases."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import time

import requests

from .. import config

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY_ID = "default"
CATEGORY_TYPE = "UNSTRUCTURED"
SOURCE_TYPE = "DATA_CENTER_FILE"
STRUCTURE_TYPE = "unstructured"
SINK_TYPE = "BUILT_IN"
PARSER = "AUTO_SELECT"

SUPPORTED_EXTENSIONS = {
    ".doc", ".docx", ".wps", ".ppt", ".pptx", ".xls", ".xlsx",
    ".md", ".txt", ".pdf", ".epub", ".mobi",
}
PARSE_READY_STATUSES = {
    "PARSE_SUCCESS",
    "INDEX_BUILD_SUCCESS",
    "FILE_IS_READY",
}
PARSE_PENDING_STATUSES = {
    "INIT",
    "IN_PARSE_QUEUE",
    "PARSING",
    "SAFE_CHECKING",
    "INDEX_BUILDING",
}
PARSE_FAILED_STATUSES = {
    "PARSE_FAILED",
    "SAFE_CHECK_FAILED",
    "INDEX_BUILDING_FAILED",
    "FILE_EXPIRED",
}


@dataclass(frozen=True)
class UploadedDocument:
    file_id: str
    file_name: str
    size_bytes: int
    checksum: str


@dataclass(frozen=True)
class ProvisionResult:
    index_id: str
    job_id: str
    job_status: str
    documents: list[UploadedDocument]
    mode: str

    @property
    def document_ids(self) -> list[str]:
        return [item.file_id for item in self.documents]


@dataclass(frozen=True)
class IndexJobStatus:
    status: str
    documents: list[dict[str, str]]


class AliyunBailianKnowledgeManager:
    """Upload documents and create or update one cloud knowledge base."""

    def __init__(
        self,
        *,
        client=None,
        models_module=None,
        runtime_factory=None,
        http_session=None,
        sleep=None,
        monotonic=None,
    ):
        self.client = client
        self.models_module = models_module
        self.runtime_factory = runtime_factory
        self.http = http_session or requests
        self.sleep = sleep or time.sleep
        self.monotonic = monotonic or time.monotonic

    def provision(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str,
        uploads: list,
        tags: list[str],
        index_id: str = "",
    ) -> ProvisionResult:
        workspace_id = str(workspace_id or "").strip()
        name = str(name or "").strip()
        index_id = str(index_id or "").strip()
        if not workspace_id:
            raise ValueError("Workspace ID 不能为空")
        if not name:
            raise ValueError("知识库名称不能为空")
        self._validate_uploads(uploads)
        self._ensure_sdk()

        documents = [
            self._upload_one(workspace_id, upload, tags)
            for upload in uploads
        ]
        document_ids = [item.file_id for item in documents]
        if index_id:
            job_id = self._submit_add_documents(
                workspace_id,
                index_id,
                document_ids,
            )
            mode = "append"
        else:
            index_id = self._create_index(
                workspace_id,
                name,
                description,
                document_ids,
            )
            job_id = self._submit_create_index(
                workspace_id,
                index_id,
            )
            mode = "create"

        return ProvisionResult(
            index_id=index_id,
            job_id=job_id,
            job_status="PENDING",
            documents=documents,
            mode=mode,
        )

    def get_job_status(
        self,
        *,
        workspace_id: str,
        index_id: str,
        job_id: str,
    ) -> IndexJobStatus:
        self._ensure_sdk()
        request = self.models_module.GetIndexJobStatusRequest(
            index_id=index_id,
            job_id=job_id,
            page_number=1,
            page_size=100,
        )
        response = self.client.get_index_job_status_with_options(
            workspace_id,
            request,
            {},
            self.runtime_factory(),
        )
        data = self._response_data(response, "查询索引任务状态")
        status = str(self._field(data, "status", "") or "").strip().upper()
        documents = []
        for item in self._field(data, "documents", []) or []:
            documents.append({
                "id": str(self._field(item, "doc_id", "") or ""),
                "name": str(self._field(item, "doc_name", "") or ""),
                "status": str(self._field(item, "status", "") or ""),
                "message": str(self._field(item, "message", "") or ""),
            })
        return IndexJobStatus(status=status, documents=documents)

    def list_cloud_documents(
        self,
        *,
        workspace_id: str,
        index_id: str,
    ) -> list[dict]:
        """List all documents in a cloud index via ListIndexDocuments."""
        self._ensure_sdk()
        all_documents: list[dict] = []
        page_number = 1
        page_size = 100
        while True:
            request = self.models_module.ListIndexDocumentsRequest(
                index_id=index_id,
                page_number=page_number,
                page_size=page_size,
            )
            response = self.client.list_index_documents_with_options(
                workspace_id,
                request,
                {},
                self.runtime_factory(),
            )
            data = self._response_data(response, "列出知识库文档")
            documents = self._field(data, "documents", []) or []
            for item in documents:
                all_documents.append({
                    "id": str(self._field(item, "id", "") or ""),
                    "name": str(self._field(item, "name", "") or ""),
                    "status": str(self._field(item, "status", "") or ""),
                    "size": int(self._field(item, "size", 0) or 0),
                    "code": str(self._field(item, "code", "") or ""),
                    "message": str(self._field(item, "message", "") or ""),
                    "source_id": str(self._field(item, "source_id", "") or ""),
                    "document_type": str(
                        self._field(item, "document_type", "") or ""
                    ),
                })
            total = int(self._field(data, "total_count", 0) or 0)
            if page_number * page_size >= total:
                break
            page_number += 1
        return all_documents

    def _upload_one(
        self,
        workspace_id: str,
        upload,
        tags: list[str],
    ) -> UploadedDocument:
        file_name, size, md5_value = self._file_info(upload)
        lease_request = self.models_module.ApplyFileUploadLeaseRequest(
            category_type=CATEGORY_TYPE,
            file_name=file_name,
            md_5=md5_value,
            size_in_bytes=str(size),
            use_internal_endpoint=False,
        )
        lease_response = self.client.apply_file_upload_lease_with_options(
            DEFAULT_CATEGORY_ID,
            workspace_id,
            lease_request,
            {},
            self.runtime_factory(),
        )
        lease_data = self._response_data(lease_response, "申请文件上传租约")
        lease_id = str(
            self._field(lease_data, "file_upload_lease_id", "") or ""
        ).strip()
        param = self._field(lease_data, "param", {})
        upload_url = str(self._field(param, "url", "") or "").strip()
        method = str(self._field(param, "method", "PUT") or "PUT").upper()
        headers = self._normalize_headers(
            self._field(param, "headers", {})
        )
        if not lease_id or not upload_url:
            raise RuntimeError("百炼未返回有效的上传租约或上传地址")

        upload.file.seek(0)
        try:
            response = self.http.request(
                method,
                upload_url,
                headers=headers,
                data=upload.file,
                timeout=config.KNOWLEDGE_UPLOAD_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                f"上传文件到百炼临时存储失败: {file_name}"
            ) from exc

        add_request = self.models_module.AddFileRequest(
            category_id=DEFAULT_CATEGORY_ID,
            category_type=CATEGORY_TYPE,
            lease_id=lease_id,
            parser=PARSER,
            tags=self._normalize_tags(tags),
        )
        add_response = self.client.add_file_with_options(
            workspace_id,
            add_request,
            {},
            self.runtime_factory(),
        )
        add_data = self._response_data(add_response, "添加文件")
        file_id = str(self._field(add_data, "file_id", "") or "").strip()
        if not file_id:
            raise RuntimeError("百炼 AddFile 未返回 FileId")
        self._wait_for_parse(workspace_id, file_id)
        return UploadedDocument(
            file_id=file_id,
            file_name=file_name,
            size_bytes=size,
            checksum=md5_value,
        )

    def delete_document(
        self,
        *,
        workspace_id: str,
        index_id: str,
        file_id: str,
    ) -> bool:
        """Remove a file from retrieval, then best-effort delete its source."""
        self._ensure_sdk()
        request = self.models_module.DeleteIndexDocumentRequest(
            index_id=index_id,
            document_ids=[file_id],
        )
        response = self.client.delete_index_document_with_options(
            workspace_id,
            request,
            {},
            self.runtime_factory(),
        )
        self._response_data(response, "删除知识库文档")

        try:
            source_response = self.client.delete_file_with_options(
                file_id,
                workspace_id,
                self.models_module.DeleteFileRequest(),
                {},
                self.runtime_factory(),
            )
            self._response_data(source_response, "清理源文件")
        except Exception as exc:
            logger.warning(
                "Knowledge source cleanup failed for file %s: %s",
                file_id,
                exc,
            )
            return False
        return True

    def _wait_for_parse(self, workspace_id: str, file_id: str) -> None:
        deadline = (
            self.monotonic()
            + config.KNOWLEDGE_FILE_PARSE_TIMEOUT_SECONDS
        )
        auth_retry_deadline = self.monotonic() + 30
        while True:
            try:
                response = self.client.describe_file_with_options(
                    workspace_id,
                    file_id,
                    self.models_module.DescribeFileRequest(),
                    {},
                    self.runtime_factory(),
                )
                data = self._response_data(response, "查询文件解析状态")
            except RuntimeError as exc:
                if "NOT AUTHORIZED" in str(exc) and self.monotonic() < auth_retry_deadline:
                    self.sleep(5)
                    continue
                raise
            status = str(
                self._field(data, "status", "") or ""
            ).strip().upper()
            if status in PARSE_READY_STATUSES:
                return
            if status in PARSE_FAILED_STATUSES:
                detail = str(
                    self._field(data, "parse_error_message", "") or ""
                ).strip()
                raise RuntimeError(
                    f"文件解析失败: {status}"
                    + (f" - {detail}" if detail else "")
                )
            if status not in PARSE_PENDING_STATUSES:
                raise RuntimeError(f"未知的文件解析状态: {status or '<empty>'}")
            if self.monotonic() >= deadline:
                raise TimeoutError(
                    f"等待文件解析超时: file_id={file_id}"
                )
            self.sleep(config.KNOWLEDGE_FILE_POLL_INTERVAL_SECONDS)

    def _create_index(
        self,
        workspace_id: str,
        name: str,
        description: str,
        document_ids: list[str],
    ) -> str:
        request = self.models_module.CreateIndexRequest(
            name=name,
            description=description,
            structure_type=STRUCTURE_TYPE,
            source_type=SOURCE_TYPE,
            sink_type=SINK_TYPE,
            document_ids=document_ids,
            rerank_min_score=config.KNOWLEDGE_RETRIEVAL_MIN_SCORE,
            enable_rewrite=True,
        )
        response = self.client.create_index_with_options(
            workspace_id,
            request,
            {},
            self.runtime_factory(),
        )
        data = self._response_data(response, "创建知识库")
        if isinstance(data, dict):
            index_id = str(data.get("id") or data.get("Id") or "").strip()
        else:
            index_id = str(
                getattr(data, "id", "")
                or getattr(data, "Id", "")
                or getattr(data, "index_id", "")
                or ""
            ).strip()
        if not index_id:
            raw = data.to_map() if hasattr(data, "to_map") else str(data)
            raise RuntimeError(f"百炼 CreateIndex 未返回 IndexId, 返回内容: {raw}")
        return index_id

    def _submit_create_index(
        self,
        workspace_id: str,
        index_id: str,
    ) -> str:
        request = self.models_module.SubmitIndexJobRequest(
            index_id=index_id
        )
        response = self.client.submit_index_job_with_options(
            workspace_id,
            request,
            {},
            self.runtime_factory(),
        )
        return self._job_id(response, "提交知识库创建任务")

    def _submit_add_documents(
        self,
        workspace_id: str,
        index_id: str,
        document_ids: list[str],
    ) -> str:
        request = self.models_module.SubmitIndexAddDocumentsJobRequest(
            index_id=index_id,
            source_type=SOURCE_TYPE,
            document_ids=document_ids,
        )
        response = (
            self.client.submit_index_add_documents_job_with_options(
                workspace_id,
                request,
                {},
                self.runtime_factory(),
            )
        )
        return self._job_id(response, "提交知识库追加任务")

    def _job_id(self, response, operation: str) -> str:
        data = self._response_data(response, operation)
        job_id = str(self._field(data, "id", "") or "").strip()
        if not job_id:
            raise RuntimeError(f"百炼{operation}未返回 JobId")
        return job_id

    def _ensure_sdk(self) -> None:
        if (
            self.client is not None
            and self.models_module is not None
            and self.runtime_factory is not None
        ):
            return
        if (
            not config.ALIYUN_BAILIAN_ACCESS_KEY_ID
            or not config.ALIYUN_BAILIAN_ACCESS_KEY_SECRET
        ):
            raise ValueError(
                "未配置 ALIBABA_CLOUD_ACCESS_KEY_ID / "
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET"
            )
        try:
            from alibabacloud_bailian20231229 import models
            from alibabacloud_bailian20231229.client import Client
            from alibabacloud_tea_openapi import models as open_api_models
            from alibabacloud_tea_util import models as util_models
        except ImportError as exc:
            raise RuntimeError(
                "缺少阿里云百炼 SDK，请重新安装 backend 依赖"
            ) from exc

        sdk_config = open_api_models.Config(
            access_key_id=config.ALIYUN_BAILIAN_ACCESS_KEY_ID,
            access_key_secret=config.ALIYUN_BAILIAN_ACCESS_KEY_SECRET,
        )
        sdk_config.endpoint = config.ALIYUN_BAILIAN_ENDPOINT
        self.client = Client(sdk_config)
        self.models_module = models
        self.runtime_factory = lambda: util_models.RuntimeOptions(
            connect_timeout=int(
                config.KNOWLEDGE_UPLOAD_HTTP_TIMEOUT_SECONDS * 1000
            ),
            read_timeout=int(
                config.KNOWLEDGE_UPLOAD_HTTP_TIMEOUT_SECONDS * 1000
            ),
            autoretry=False,
        )

    @staticmethod
    def _validate_uploads(uploads: list) -> None:
        if not uploads:
            raise ValueError("请至少上传一个知识库文档")
        if len(uploads) > config.KNOWLEDGE_UPLOAD_MAX_FILES:
            raise ValueError(
                f"单次最多上传 {config.KNOWLEDGE_UPLOAD_MAX_FILES} 个文件"
            )
        for upload in uploads:
            file_name = Path(str(upload.filename or "")).name
            if len(file_name) < 4 or len(file_name) > 128:
                raise ValueError(
                    f"文件名长度必须为 4-128 个字符: {file_name or '<empty>'}"
                )
            suffix = Path(file_name).suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                raise ValueError(f"不支持的知识库文件类型: {suffix or '<none>'}")

    @staticmethod
    def _file_info(upload) -> tuple[str, int, str]:
        file_name = Path(str(upload.filename or "")).name
        upload.file.seek(0)
        digest = hashlib.md5()
        size = 0
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > config.KNOWLEDGE_UPLOAD_MAX_FILE_BYTES:
                raise ValueError(
                    f"文件超过大小限制: {file_name}"
                )
            digest.update(chunk)
        upload.file.seek(0)
        if size <= 0:
            raise ValueError(f"上传文件为空: {file_name}")
        return file_name, size, digest.hexdigest()

    @staticmethod
    def _normalize_tags(tags: list[str]) -> list[str]:
        result = []
        for value in tags[:100]:
            tag = str(value or "").strip()[:32]
            if tag and tag not in result:
                result.append(tag)
        return result

    @classmethod
    def _normalize_headers(cls, value) -> dict[str, str]:
        if hasattr(value, "to_map"):
            value = value.to_map()
        if isinstance(value, str):
            text = value.strip()
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                try:
                    value = json.loads("{" + text + "}")
                except json.JSONDecodeError as exc:
                    raise RuntimeError("百炼返回的上传请求头格式无效") from exc
        if not isinstance(value, dict):
            return {}
        return {
            str(key): "" if item is None else str(item)
            for key, item in value.items()
        }

    @classmethod
    def _response_data(cls, response, operation: str):
        body = cls._field(response, "body", response)
        success = cls._field(body, "success", True)
        code = str(cls._field(body, "code", "") or "")
        if str(success).lower() == "false" or (code and code != "Success"):
            message = str(cls._field(body, "message", "") or "")
            raise RuntimeError(
                f"百炼{operation}失败: {code or '<unknown>'} "
                f"{message or '<empty>'}"
            )
        return cls._field(body, "data", {})

    @staticmethod
    def _field(value, name: str, default=None):
        if isinstance(value, dict):
            if name in value:
                return value[name]
            pascal_name = "".join(
                part.capitalize()
                for part in name.split("_")
            )
            return value.get(pascal_name, default)
        return getattr(value, name, default)
