"""MaxKB application provider.

The MaxKB application owns the knowledge retrieval pipeline and the cloud
model binding.  This adapter therefore treats MaxKB as a direct-answer
provider instead of returning chunks for this repo to answer again.
"""

from __future__ import annotations

from typing import Any

import requests

from .. import config
from ..configuration.models import KnowledgeBase


class MaxKBKnowledgeClient:
    """Query MaxKB's OpenAI-compatible application chat API."""

    provider = "maxkb"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        chat_path: str | None = None,
        timeout_seconds: float | None = None,
        http_session: Any = None,
    ):
        self._base_url = (base_url or config.MAXKB_BASE_URL).rstrip("/")
        self._api_key = api_key or config.MAXKB_API_KEY
        self._chat_path = "/" + (chat_path or config.MAXKB_CHAT_PATH).strip("/")
        self._timeout = float(
            timeout_seconds
            if timeout_seconds is not None
            else config.MAXKB_TIMEOUT_SECONDS
        )
        self._session = http_session or requests

    def validate(self, knowledge_bases: list[KnowledgeBase]) -> None:
        if not self._api_key or self._api_key.startswith("your-"):
            raise ValueError("MaxKB API Key 未配置")
        if not self._base_url:
            raise ValueError("MaxKB Base URL 未配置")

        for kb in knowledge_bases:
            if kb.provider != self.provider:
                raise ValueError(
                    f"知识库 {kb.id} 的 provider 为 {kb.provider}，"
                    f"但当前 client 仅支持 {self.provider}"
                )
            if not kb.maxkb_app_id or kb.maxkb_app_id.startswith("your-"):
                raise ValueError(f"MaxKB 知识库 {kb.id} 缺少 maxkbAppId")

    def search(
        self,
        knowledge_bases: list[KnowledgeBase],
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Compatibility wrapper for RAGEngine's provider protocol."""
        _ = top_k
        answer = self.answer(knowledge_bases, query)
        if not answer:
            return []
        kb = self._select_application(knowledge_bases)
        return [{
            "title": kb.name,
            "content": answer,
            "source_name": f"{kb.name} / MaxKB App",
            "url": "",
            "score": 1.0,
            "knowledge_base_id": kb.id,
            "metadata": {"appId": kb.maxkb_app_id, "directAnswer": True},
            "chunk_id": "maxkb-direct-answer",
            "source": f"{kb.name} / MaxKB App",
            "provider": "maxkb",
            "kb_id": kb.id,
            "kb_name": kb.name,
            "kb_tags": list(kb.tags or []),
            "priority": kb.priority,
            "_score": 1.0,
            "_metadata": {"app_id": kb.maxkb_app_id, "direct_answer": True},
        }]

    def answer(
        self,
        knowledge_bases: list[KnowledgeBase],
        query: str,
        chat_history: list[dict] | None = None,
    ) -> str:
        self.validate(knowledge_bases)
        kb = self._select_application(knowledge_bases)
        messages = self._build_messages(query, chat_history)
        url = f"{self._chat_api_root()}/{kb.maxkb_app_id}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "messages": messages,
            "stream": False,
        }

        response = self._session.post(
            url,
            json=payload,
            headers=headers,
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(self._error_message(response))
        data = response.json()
        content = self._extract_content(data)
        if not content:
            raise RuntimeError("MaxKB 未返回有效回答")
        return content

    def _chat_api_root(self) -> str:
        if self._base_url.endswith(self._chat_path):
            return self._base_url
        return f"{self._base_url}{self._chat_path}"

    @staticmethod
    def _select_application(knowledge_bases: list[KnowledgeBase]) -> KnowledgeBase:
        return sorted(
            knowledge_bases,
            key=lambda item: item.priority,
            reverse=True,
        )[0]

    @staticmethod
    def _build_messages(
        query: str,
        chat_history: list[dict] | None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for item in (chat_history or [])[-6:]:
            role = str(item.get("role", "") or "").strip()
            if role not in {"user", "assistant", "system"}:
                continue
            content = str(item.get("content", "") or "").strip()
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": query})
        return messages

    @staticmethod
    def _extract_content(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                return str(message.get("content", "") or "").strip()
            delta = choices[0].get("delta", {})
            if isinstance(delta, dict):
                return str(delta.get("content", "") or "").strip()
        for key in ("answer", "content", "message"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        nested = data.get("data")
        if isinstance(nested, dict):
            return MaxKBKnowledgeClient._extract_content(nested)
        return ""

    @staticmethod
    def _error_message(response: Any) -> str:
        try:
            detail = response.json()
        except Exception:
            detail = {}
        if isinstance(detail, dict):
            message = (
                detail.get("message")
                or detail.get("detail")
                or detail.get("error", {}).get("message")
            )
            if message:
                return str(message)
        return f"MaxKB HTTP {response.status_code}"


class MaxKBKnowledgeManager:
    """Admin-time operations stay in MaxKB for the MVP path."""

    def provision(self, **kwargs: Any) -> Any:
        _ = kwargs
        raise NotImplementedError(
            "MaxKB 文档请在 MaxKB 控制台管理。"
            "在 MaxKB 中创建应用、绑定知识库和云端模型后，将应用 ID 填入本管理台即可。"
        )

    def get_job_status(self, **kwargs: Any) -> Any:
        _ = kwargs
        raise NotImplementedError("MaxKB 索引任务请在 MaxKB 控制台查看。")

    def list_cloud_documents(self, **kwargs: Any) -> list[dict[str, Any]]:
        _ = kwargs
        return []

    def delete_document(self, **kwargs: Any) -> bool:
        _ = kwargs
        raise NotImplementedError("MaxKB 文档删除请在 MaxKB 控制台完成。")
