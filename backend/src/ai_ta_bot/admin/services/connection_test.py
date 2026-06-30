"""Connection tests for LLM, web-search, and knowledge providers."""

from __future__ import annotations

import json
import time
from typing import Any

import requests


def test_llm(
    api_key: str,
    base_url: str = "https://api.deepseek.com",
    timeout: int = 10,
) -> dict[str, Any]:
    """Ping the OpenAI-compatible chat endpoint with a minimal request."""
    if not api_key or api_key.startswith("your-"):
        return {"ok": False, "provider": "deepseek", "latencyMs": 0, "message": "API Key 未配置或仍为示例值"}

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start = time.monotonic()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        latency = int((time.monotonic() - start) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "provider": "deepseek", "latencyMs": latency, "message": "连接成功"}
        try:
            detail = resp.json()
        except json.JSONDecodeError:
            detail = {}
        error_msg = (
            detail.get("error", {}).get("message")
            or detail.get("message")
            or f"HTTP {resp.status_code}"
        )
        return {"ok": False, "provider": "deepseek", "latencyMs": latency, "message": str(error_msg)}
    except requests.Timeout:
        latency = int((time.monotonic() - start) * 1000)
        return {"ok": False, "provider": "deepseek", "latencyMs": latency, "message": "连接超时"}
    except requests.ConnectionError as exc:
        return {"ok": False, "provider": "deepseek", "latencyMs": 0, "message": f"无法连接: {exc}"}
    except Exception as exc:
        return {"ok": False, "provider": "deepseek", "latencyMs": 0, "message": str(exc)}


def test_web_search(
    provider: str,
    api_key: str,
    timeout: int = 10,
) -> dict[str, Any]:
    """Ping the configured web-search provider with a trivial query."""
    if not api_key or api_key.startswith("your-"):
        return {"ok": False, "provider": provider, "latencyMs": 0, "message": "API Key 未配置或仍为示例值"}

    start = time.monotonic()
    try:
        if provider == "volcengine":
            return _test_volcengine(api_key, timeout, start)
        return _test_tavily(api_key, timeout, start)
    except requests.Timeout:
        latency = int((time.monotonic() - start) * 1000)
        return {"ok": False, "provider": provider, "latencyMs": latency, "message": "连接超时"}
    except requests.ConnectionError as exc:
        return {"ok": False, "provider": provider, "latencyMs": 0, "message": f"无法连接: {exc}"}
    except Exception as exc:
        return {"ok": False, "provider": provider, "latencyMs": 0, "message": str(exc)}


def _test_tavily(api_key: str, timeout: int, start: float) -> dict[str, Any]:
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": "test", "max_results": 1, "search_depth": "basic"},
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    latency = int((time.monotonic() - start) * 1000)
    if resp.status_code == 200:
        return {"ok": True, "provider": "tavily", "latencyMs": latency, "message": "连接成功"}
    detail = resp.json() if resp.text else {}
    return {"ok": False, "provider": "tavily", "latencyMs": latency, "message": str(detail.get("detail", f"HTTP {resp.status_code}"))}


def _test_volcengine(api_key: str, timeout: int, start: float) -> dict[str, Any]:
    resp = requests.post(
        "https://api.volcengine.com/web_search/v1/query",
        json={
            "api_key": api_key,
            "query": "test",
            "max_results": 1,
            "time_range": "week",
        },
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    latency = int((time.monotonic() - start) * 1000)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("code") == 0:
            return {"ok": True, "provider": "volcengine", "latencyMs": latency, "message": "连接成功"}
        return {"ok": False, "provider": "volcengine", "latencyMs": latency, "message": data.get("message", "未知错误")}
    return {"ok": False, "provider": "volcengine", "latencyMs": latency, "message": f"HTTP {resp.status_code}"}




def test_maxkb(
    base_url: str = "http://127.0.0.1:8080",
    api_key: str = "",
    timeout: int = 10,
) -> dict[str, Any]:
    """Verify MaxKB application API key via the chat profile endpoint."""
    if not api_key or api_key.startswith("your-"):
        return {"ok": False, "provider": "maxkb", "latencyMs": 0, "message": "API Key 未配置或仍为示例值"}
    if not base_url:
        return {"ok": False, "provider": "maxkb", "latencyMs": 0, "message": "Base URL 未配置"}

    root = _maxkb_chat_api_root(base_url)
    url = f"{root}/application/profile"
    headers = {"Authorization": f"Bearer {api_key}"}
    start = time.monotonic()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        latency = int((time.monotonic() - start) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "provider": "maxkb", "latencyMs": latency, "message": "连接成功"}
        message = f"HTTP {resp.status_code}"
        try:
            detail = resp.json()
        except json.JSONDecodeError:
            detail = {}
        if isinstance(detail, dict):
            message = str(detail.get("message") or detail.get("detail") or message)
        return {"ok": False, "provider": "maxkb", "latencyMs": latency, "message": message}
    except requests.Timeout:
        latency = int((time.monotonic() - start) * 1000)
        return {"ok": False, "provider": "maxkb", "latencyMs": latency, "message": "连接超时"}
    except requests.ConnectionError as exc:
        return {"ok": False, "provider": "maxkb", "latencyMs": 0, "message": f"无法连接: {exc}"}
    except Exception as exc:
        return {"ok": False, "provider": "maxkb", "latencyMs": 0, "message": str(exc)}


def _maxkb_chat_api_root(base_url: str) -> str:
    from ... import config

    root = str(base_url or "").rstrip("/")
    chat_path = str(getattr(config, "MAXKB_CHAT_PATH", "/chat/api") or "/chat/api").strip()
    if not chat_path.startswith("/"):
        chat_path = f"/{chat_path}"
    if root.endswith(chat_path):
        return root
    return f"{root}{chat_path}"
