"""API for web-managed runtime settings and provider connection tests."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ... import settings_manager
from ...config import get_effective_settings
from ..services import connection_test

router = APIRouter(tags=["settings"])


# ── settings CRUD ────────────────────────────────────────────────────────────

@router.get("/api/settings")
def get_settings() -> dict[str, Any]:
    effective = get_effective_settings()
    public = settings_manager.public_settings(effective)
    return {
        "ok": True,
        "settings": public,
        "savedAt": settings_manager.saved_at(),
    }


@router.post("/api/settings")
def save_settings(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    existing = settings_manager.read_settings()
    merged = settings_manager.merge_settings(payload, existing)
    written = settings_manager.write_settings(merged)
    public = settings_manager.public_settings(written)
    return {
        "ok": True,
        "settings": public,
        "savedAt": settings_manager.saved_at(),
        "message": "设置已保存，重启机器人后生效",
    }


# ── connection tests ─────────────────────────────────────────────────────────

@router.post("/api/settings/test/llm")
def test_llm(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    effective = get_effective_settings()
    api_key = _value_or(payload.get("apiKey"), effective.get("llmApiKey", ""))
    base_url = _value_or(payload.get("baseUrl"), effective.get("llmBaseUrl", ""))
    return connection_test.test_llm(api_key=api_key, base_url=base_url)


@router.post("/api/settings/test/search")
def test_search(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    effective = get_effective_settings()
    provider = _value_or(payload.get("provider"), effective.get("webSearchProvider", "tavily"))
    if provider == "volcengine":
        default_key = effective.get("volcengineApiKey", "")
    else:
        default_key = effective.get("tavilyApiKey", "")
    api_key = _value_or(payload.get("apiKey"), default_key)
    return connection_test.test_web_search(provider=provider, api_key=api_key)


@router.post("/api/settings/test/knowledge")
def test_knowledge(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    effective = get_effective_settings()
    access_key_id = _value_or(
        payload.get("accessKeyId"),
        effective.get("aliyunAccessKeyId", ""),
    )
    access_key_secret = _value_or(
        payload.get("accessKeySecret"),
        effective.get("aliyunAccessKeySecret", ""),
    )
    return connection_test.test_knowledge_provider(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
    )


def _value_or(value: Any, default: str) -> str:
    """Return *value* if it is a non-empty, non-placeholder string; else *default*."""
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed and not trimmed.startswith("your-") and not trimmed.startswith("****"):
            return trimmed
    return str(default or "")
