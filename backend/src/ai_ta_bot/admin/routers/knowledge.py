"""Cloud knowledge-base provisioning endpoints."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ... import config, config_store
from ...knowledge.factory import create_knowledge_manager
from ...persistence import KnowledgeDocumentRepository

router = APIRouter(tags=["knowledge"])
logger = logging.getLogger(__name__)


def _manager_factory(provider: str = "maxkb"):
    return create_knowledge_manager(provider)


def _repository_factory() -> KnowledgeDocumentRepository:
    return KnowledgeDocumentRepository(config.BOT_STATE_DB)


def _configured_value(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.startswith("your-") else text


def _public_knowledge_base(item: dict) -> dict:
    return config_store.public_config({
        "knowledgeBases": [item],
    })["knowledgeBases"][0]


def _public_document(item: dict) -> dict:
    result = dict(item)
    result.pop("knowledgeBaseId", None)
    for version in result.get("versions", []):
        version.pop("checksum", None)
        version.pop("cloudFileId", None)
        version.pop("cloudJobId", None)
        version.pop("replacesVersion", None)
        if version.get("error"):
            version["error"] = _public_error(
                RuntimeError(version["error"])
            )
    return result


def _knowledge_base(kb_id: str) -> tuple[dict, dict]:
    config_data = config_store.read_config()
    knowledge_base = next(
        (
            item
            for item in config_data.get("knowledgeBases", [])
            if item.get("id") == kb_id
        ),
        None,
    )
    if knowledge_base is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return config_data, knowledge_base



def _public_error(exc: Exception) -> str:
    text = str(exc)
    internal_markers = (
        "ALIBABA_CLOUD",
        "Workspace",
        "workspace",
        "百炼",
        "AccessKey",
    )
    if any(marker in text for marker in internal_markers):
        return "知识库服务暂不可用，请联系平台管理员"
    return text


@router.post("/api/knowledge/provision")
def provision_knowledge_base(
    knowledge_base: str = Form(...),
    files: list[UploadFile] = File(...),
):
    try:
        draft = json.loads(knowledge_base)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="知识库配置不是有效 JSON",
        ) from exc
    if not isinstance(draft, dict):
        raise HTTPException(status_code=400, detail="知识库配置格式错误")

    kb_id = str(draft.get("id", "")).strip()
    name = str(draft.get("name", "")).strip()
    if not kb_id:
        raise HTTPException(status_code=400, detail="知识库 ID 不能为空")

    try:
        current = config_store.read_config()
        existing = next(
            (
                item
                for item in current.get("knowledgeBases", [])
                if item.get("id") == kb_id
            ),
            {},
        )
        provider = existing.get("provider") or draft.get("provider") or "maxkb"
        if provider == "maxkb":
            raise HTTPException(
                status_code=400,
                detail="MaxKB 文档上传请在 MaxKB 控制台完成。"
                       "在 MaxKB 中创建应用、绑定知识库和云端模型后，"
                       "将应用 ID 填入本管理台的知识库配置即可。",
            )


        manager = _manager_factory(provider)
        result = manager.provision(
            workspace_id="",
            name=name,
            description=str(draft.get("description", "")).strip(),
            uploads=files,
            tags=[
                str(item).strip()
                for item in draft.get("tags", [])
                if str(item).strip()
            ],
            index_id="",
        )

        document_ids = list(dict.fromkeys([
            *existing.get("documentIds", []),
            *result.document_ids,
        ]))
        updated_item = {
            **existing,
            **draft,
            "id": kb_id,
            "provider": provider,
            "workspaceId": "",
            "indexId": result.index_id,
            "indexJobId": result.job_id,
            "indexStatus": result.job_status,
            "documentIds": document_ids,
        }
        saved = config_store.upsert_knowledge_base(updated_item)
        saved_item = next(
            item
            for item in saved["knowledgeBases"]
            if item["id"] == kb_id
        )
        repository = _repository_factory()
        created_documents = [
            repository.create_pending(
                knowledge_base_id=kb_id,
                file_name=item.file_name,
                size_bytes=item.size_bytes,
                checksum=item.checksum,
                cloud_file_id=item.file_id,
                cloud_job_id=result.job_id,
            )
            for item in result.documents
        ]
    except (ValueError, RuntimeError, TimeoutError) as exc:
        logger.warning("Knowledge provisioning failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=_public_error(exc),
        ) from exc
    finally:
        for upload in files:
            upload.file.close()

    return {
        "ok": True,
        "mode": result.mode,
        "message": (
            "知识库创建任务已提交"
            if result.mode == "create"
            else "知识库文档追加任务已提交"
        ),
        "knowledgeBase": _public_knowledge_base(saved_item),
        "documents": [
            _public_document(item)
            for item in created_documents
        ],
        "config": config_store.public_config(saved),
    }


@router.get("/api/knowledge/{kb_id}/documents")
def list_knowledge_documents(kb_id: str):
    _, knowledge_base = _knowledge_base(kb_id)
    repository = _repository_factory()

    # MaxKB provider: documents managed in MaxKB console
    if False:
        try:
            manager = _manager_factory()
            cloud_docs = manager.list_cloud_documents(
                workspace_id="",
                index_id="",
            )
            repository.sync_from_cloud(kb_id, cloud_docs)
        except Exception as exc:
            logger.warning("Cloud sync for KB %s failed, using local cache: %s", kb_id, exc)

    documents = repository.list(kb_id)
    return {
        "ok": True,
        "documents": [
            _public_document(item)
            for item in documents
        ],
    }


@router.post("/api/knowledge/{kb_id}/documents/{document_id}/replace")
def replace_knowledge_document(
    kb_id: str,
    document_id: str,
    file: UploadFile = File(...),
):
    try:
        _, knowledge_base = _knowledge_base(kb_id)
        # MaxKB provider: document management in MaxKB console
        raise ValueError("文档管理请在 MaxKB 控制台完成")

        repository = _repository_factory()
        current = repository.get(document_id, include_internal=True)
        if not current or current.get("knowledgeBaseId") != kb_id:
            raise HTTPException(status_code=404, detail="文档不存在")
        if current.get("status") in {
            "PROCESSING",
            "UPDATING",
            "DELETING",
        }:
            raise ValueError("文档正在处理中，请稍后再试")
        if current.get("status") == "DELETED":
            raise ValueError("已删除的文档不能替换")
        if not current.get("currentVersion"):
            raise ValueError("文档尚无可替换的有效版本")

        result = _manager_factory().provision(
            workspace_id="",
            name=str(knowledge_base.get("name", "")).strip(),
            description=str(
                knowledge_base.get("description", "")
            ).strip(),
            uploads=[file],
            tags=[
                str(item).strip()
                for item in knowledge_base.get("tags", [])
                if str(item).strip()
            ],
            index_id=index_id,
        )
        uploaded = result.documents[0]
        updated = repository.start_replacement(
            document_id,
            file_name=uploaded.file_name,
            size_bytes=uploaded.size_bytes,
            checksum=uploaded.checksum,
            cloud_file_id=uploaded.file_id,
            cloud_job_id=result.job_id,
        )
        saved = config_store.update_knowledge_cloud_state(
            kb_id,
            index_job_id=result.job_id,
            index_status=result.job_status,
            document_ids=repository.active_cloud_file_ids(kb_id),
        )
    except HTTPException:
        raise
    except (ValueError, RuntimeError, TimeoutError) as exc:
        logger.warning("Knowledge document replacement failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=_public_error(exc),
        ) from exc
    finally:
        file.file.close()

    return {
        "ok": True,
        "message": "新版本已上传，处理完成后会自动替换旧版本",
        "document": _public_document(updated),
        "config": config_store.public_config(saved),
    }


@router.delete("/api/knowledge/{kb_id}/documents/{document_id}")
def delete_knowledge_document(kb_id: str, document_id: str):
    try:
        _, knowledge_base = _knowledge_base(kb_id)
        # MaxKB provider: document management in MaxKB console
        raise ValueError("文档管理请在 MaxKB 控制台完成")

        repository = _repository_factory()
        current = repository.get(document_id, include_internal=True)
        if not current or current.get("knowledgeBaseId") != kb_id:
            raise HTTPException(status_code=404, detail="文档不存在")
        if current.get("status") == "DELETED":
            return {
                "ok": True,
                "message": "文档已删除",
                "document": _public_document(current),
            }
        if current.get("status") in {
            "PROCESSING",
            "UPDATING",
            "DELETING",
        }:
            raise ValueError("文档正在处理中，请稍后再试")
        current_version = current.get("currentVersion")
        version = next(
            (
                item
                for item in current.get("versions", [])
                if item.get("version") == current_version
            ),
            current.get("versions", [None])[0]
            if current.get("versions")
            else None,
        )
        if version is None:
            raise ValueError("文档尚无可删除的有效版本")

        source_cleaned = _manager_factory().delete_document(
            workspace_id="",
            index_id="",
            file_id=version["cloudFileId"],
        )
        deleted = repository.mark_deleted(document_id)
        saved = config_store.update_knowledge_cloud_state(
            kb_id,
            document_ids=repository.active_cloud_file_ids(kb_id),
        )
    except HTTPException:
        raise
    except (ValueError, RuntimeError, TimeoutError) as exc:
        logger.warning("Knowledge document deletion failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=_public_error(exc),
        ) from exc

    return {
        "ok": True,
        "message": (
            "文档已删除"
            if source_cleaned
            else "文档已从知识库移除，后台源文件将在后续清理"
        ),
        "document": _public_document(deleted),
        "config": config_store.public_config(saved),
    }


@router.get("/api/knowledge/{kb_id}/job")
def get_knowledge_job(kb_id: str):
    _, knowledge_base = _knowledge_base(kb_id)
    job_id = _configured_value(knowledge_base.get("indexJobId"))
    if not job_id:
        raise HTTPException(
            status_code=400,
            detail="知识库尚无可查询的索引任务",
        )

    try:
        manager = _manager_factory()
        repository = _repository_factory()
        result = manager.get_job_status(
            workspace_id="",
            index_id="",
            job_id=job_id,
        )
        if result.status == "FAILED":
            error = next(
                (
                    item.get("message")
                    for item in result.documents
                    if item.get("message")
                ),
                "文档处理失败",
            )
            repository.fail_job(job_id, error)
        elif result.status == "COMPLETED":
            statuses = {
                item.get("id"): item
                for item in result.documents
            }
            for pending in repository.pending_versions_for_job(job_id):
                cloud_status = statuses.get(
                    pending["cloud_file_id"],
                    {},
                )
                if (
                    cloud_status
                    and cloud_status.get("status") not in {"FINISH", ""}
                ):
                    repository.fail_version(
                        pending["document_id"],
                        pending["version"],
                        cloud_status.get("message") or "文档导入失败",
                    )
                    continue
                if pending.get("replaces_version"):
                    current = repository.get(
                        pending["document_id"],
                        include_internal=True,
                    )
                    old_version = next(
                        item
                        for item in current["versions"]
                        if item["version"] == pending["replaces_version"]
                    )
                    manager.delete_document(
                        workspace_id=workspace_id,
                        index_id=index_id,
                        file_id=old_version["cloudFileId"],
                    )
                repository.activate_version(
                    pending["document_id"],
                    pending["version"],
                )
        saved = config_store.update_knowledge_cloud_state(
            kb_id,
            index_status=result.status,
            document_ids=repository.active_cloud_file_ids(kb_id),
        )
    except (ValueError, RuntimeError) as exc:
        logger.warning("Knowledge job status query failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=_public_error(exc),
        ) from exc

    return {
        "ok": True,
        "status": result.status,
        "documents": [
            {
                "name": item.get("name", ""),
                "status": item.get("status", ""),
                "message": (
                    _public_error(RuntimeError(item["message"]))
                    if item.get("message")
                    else ""
                ),
            }
            for item in result.documents
        ],
        "documentRecords": [
            _public_document(item)
            for item in repository.list(kb_id)
        ],
        "config": config_store.public_config(saved),
    }
