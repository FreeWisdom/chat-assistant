"""Cloud knowledge-base retrieval adapters."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from .. import config
from ..configuration import KnowledgeBase

logger = logging.getLogger(__name__)


class AliyunBailianKnowledgeClient:
    """Retrieve normalized chunks from Alibaba Cloud Model Studio."""

    provider = "aliyun_bailian"

    def __init__(
        self,
        *,
        client=None,
        models_module=None,
        runtime_factory=None,
        min_score: float | None = None,
        timeout_seconds: float | None = None,
        max_attempts: int | None = None,
    ):
        self.client = client
        self.models_module = models_module
        self.runtime_factory = runtime_factory
        self.min_score = (
            config.KNOWLEDGE_RETRIEVAL_MIN_SCORE
            if min_score is None
            else min_score
        )
        self.timeout_seconds = (
            config.KNOWLEDGE_RETRIEVAL_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self.max_attempts = max(
            1,
            config.KNOWLEDGE_RETRIEVAL_MAX_ATTEMPTS
            if max_attempts is None
            else max_attempts,
        )

    def validate(self, knowledge_bases: list[KnowledgeBase]) -> None:
        unsupported = [
            kb.id
            for kb in knowledge_bases
            if kb.provider != self.provider
        ]
        if unsupported:
            raise ValueError(
                f"只支持阿里云百炼知识库，以下 provider 无效: {unsupported}"
            )

        incomplete = [
            kb.id
            for kb in knowledge_bases
            if not kb.workspace_id or not kb.index_id
        ]
        if incomplete:
            raise ValueError(
                f"阿里云百炼知识库缺少 workspaceId 或 indexId: {incomplete}"
            )

        if knowledge_bases and self.client is None and (
            not config.ALIYUN_BAILIAN_ACCESS_KEY_ID
            or not config.ALIYUN_BAILIAN_ACCESS_KEY_SECRET
        ):
            raise ValueError(
                "未配置 ALIBABA_CLOUD_ACCESS_KEY_ID / "
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET"
            )

    def search(
        self,
        knowledge_bases: list[KnowledgeBase],
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        self.validate(knowledge_bases)
        self._ensure_sdk()

        results: list[dict[str, Any]] = []
        for kb in knowledge_bases:
            results.extend(self._retrieve_one(kb, query, top_k))

        results.sort(
            key=lambda item: (
                float(item.get("_score", 0) or 0),
                float(item.get("priority", 0) or 0),
            ),
            reverse=True,
        )
        return results[:max(1, top_k)]

    def _ensure_sdk(self) -> None:
        if (
            self.client is not None
            and self.models_module is not None
            and self.runtime_factory is not None
        ):
            return

        try:
            from alibabacloud_bailian20231229 import (
                models as bailian_models,
            )
            from alibabacloud_bailian20231229.client import (
                Client as BailianClient,
            )
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
        self.client = BailianClient(sdk_config)
        self.models_module = bailian_models
        self.runtime_factory = lambda: util_models.RuntimeOptions(
            connect_timeout=int(self.timeout_seconds * 1000),
            read_timeout=int(self.timeout_seconds * 1000),
            autoretry=False,
        )

    def _retrieve_one(
        self,
        kb: KnowledgeBase,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        candidate_top_k = min(max(top_k * 4, 10), 100)
        request = self.models_module.RetrieveRequest(
            index_id=kb.index_id,
            query=query,
            dense_similarity_top_k=candidate_top_k,
            sparse_similarity_top_k=candidate_top_k,
            enable_reranking=True,
            rerank_min_score=self.min_score,
            rerank_top_n=min(max(top_k, 1), 20),
            save_retriever_history=False,
        )

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.client.retrieve_with_options(
                    kb.workspace_id,
                    request,
                    {},
                    self.runtime_factory(),
                )
                return self._normalize_response(kb, response)
            except Exception as exc:
                if attempt >= self.max_attempts:
                    logger.error(
                        "阿里云百炼检索失败: kb=%s attempts=%s error=%s",
                        kb.id,
                        attempt,
                        exc,
                    )
                    return []
                logger.warning(
                    "阿里云百炼检索失败，准备重试: kb=%s attempt=%s error=%s",
                    kb.id,
                    attempt,
                    exc,
                )
                time.sleep(min(2 ** (attempt - 1), 4))
        return []

    def _normalize_response(
        self,
        kb: KnowledgeBase,
        response,
    ) -> list[dict[str, Any]]:
        body = self._field(response, "body", response)
        success = self._field(body, "success", True)
        if success is False:
            logger.warning(
                "阿里云百炼检索返回失败: kb=%s request_id=%s code=%s message=%s",
                kb.id,
                self._field(body, "request_id", ""),
                self._field(body, "code", ""),
                self._field(body, "message", ""),
            )
            return []

        data = self._field(body, "data", {})
        nodes = self._field(data, "nodes", []) or []
        normalized: list[dict[str, Any]] = []
        for index, node in enumerate(nodes):
            text = str(self._field(node, "text", "") or "").strip()
            score = float(self._field(node, "score", 0) or 0)
            if not text or score < self.min_score:
                continue
            metadata = self._metadata(
                self._field(node, "metadata", {})
            )
            source = str(
                metadata.get("doc_name")
                or metadata.get("title")
                or metadata.get("hier_title")
                or kb.name
            ).strip()
            normalized.append({
                "chunk_id": str(
                    metadata.get("nid")
                    or metadata.get("doc_id")
                    or f"{kb.id}-{index + 1}"
                ),
                "content": text,
                "source": source,
                "title": str(metadata.get("title") or source),
                "url": "",
                "provider": self.provider,
                "kb_id": kb.id,
                "kb_name": kb.name,
                "kb_tags": kb.tags,
                "priority": kb.priority,
                "_score": score,
                "_metadata": metadata,
            })
        return normalized

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

    @staticmethod
    def _metadata(value) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        if hasattr(value, "to_map"):
            mapped = value.to_map()
            return mapped if isinstance(mapped, dict) else {}
        return {}
