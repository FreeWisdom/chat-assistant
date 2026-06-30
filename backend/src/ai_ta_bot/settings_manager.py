"""Web-managed runtime settings persisted as config/settings.yaml.

settings.yaml overrides .env at startup.  It is NOT bot.yaml — it holds
secrets, feature flags, and listen-group config that were previously only
editable via .env.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
BACKUP_DIR = PROJECT_ROOT / "runtime" / "settings_backups"

# ── field metadata ──────────────────────────────────────────────────────────

FIELD_META: dict[str, dict[str, Any]] = {
    "llmApiKey":             {"label": "LLM API Key",              "type": "secret", "default": ""},
    "llmBaseUrl":            {"label": "LLM Base URL",             "type": "string", "default": "https://api.deepseek.com"},
    "tavilyApiKey":          {"label": "Tavily API Key",           "type": "secret", "default": ""},
    "volcengineApiKey":      {"label": "Volcengine API Key",       "type": "secret", "default": ""},
    "dryRun":                {"label": "Dry Run (试跑)",           "type": "bool",   "default": False},
    "allowRealSendConfirm":  {"label": "允许真实发送",             "type": "bool",   "default": False},
    "devMode":               {"label": "Dev Mode",                 "type": "bool",   "default": False},
    "requireListenGroups":   {"label": "要求监听白名单",          "type": "bool",   "default": True},
    "webSearchEnabled":      {"label": "启用联网搜索",            "type": "bool",   "default": False},
    "webSearchProvider":     {"label": "搜索提供商",              "type": "enum",   "default": "tavily", "options": ["tavily", "volcengine"]},
    "listenGroups":          {"label": "监听群白名单",            "type": "list",   "default": []},
    "botMentionNames":       {"label": "机器人昵称",              "type": "list",   "default": []},
    "maxkbApiKey":           {"label": "MaxKB API Key",           "type": "secret", "default": ""},
    "maxkbBaseUrl":          {"label": "MaxKB Base URL",          "type": "string", "default": "http://127.0.0.1:8080"},
}

SECRET_FIELDS = frozenset({
    key for key, meta in FIELD_META.items() if meta["type"] == "secret"
})


# ── read / write ─────────────────────────────────────────────────────────────

def read_settings() -> dict[str, Any]:
    """Return merged dict of defaults + saved values, or defaults if no file."""
    defaults = {key: meta["default"] for key, meta in FIELD_META.items()}
    if not SETTINGS_PATH.exists():
        return defaults
    try:
        raw = yaml.safe_load(SETTINGS_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    merged = dict(defaults)
    for key in FIELD_META:
        if key in raw:
            merged[key] = raw[key]
    return merged


def write_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Validate, normalise, back up, and write settings.yaml.

    Returns the normalised dict that was written.
    """
    normalised = _normalise(data)
    _backup_if_exists()
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        yaml.safe_dump(normalised, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return normalised


# ── secret handling ──────────────────────────────────────────────────────────

def mask_secret(value: str) -> str:
    if not value:
        return ""
    visible = value[-4:]
    return f"****{visible}"


def public_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with secret fields masked for browser transport."""
    result = dict(data)
    for key in SECRET_FIELDS:
        if key in result:
            result[key] = mask_secret(str(result[key] or ""))
    return result


def merge_settings(incoming: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """Merge incoming (from POST) onto existing (from file).

    - ``None`` or missing keys → keep existing value.
    - Secret fields whose value starts with ``****`` → keep existing value.
    - Otherwise → use incoming value.
    """
    merged = dict(existing)
    for key in FIELD_META:
        if key not in incoming:
            continue
        value = incoming[key]
        if value is None:
            continue
        if key in SECRET_FIELDS and isinstance(value, str) and value.startswith("****"):
            continue
        merged[key] = value
    return merged


# ── helpers ──────────────────────────────────────────────────────────────────

def _normalise(data: dict[str, Any]) -> dict[str, Any]:
    """Coerce types according to FIELD_META and drop unknown keys."""
    result: dict[str, Any] = {}
    for key, meta in FIELD_META.items():
        value = data.get(key, meta["default"])
        if value is None:
            value = meta["default"]
        if meta["type"] == "bool":
            result[key] = bool(value) if not isinstance(value, bool) else value
        elif meta["type"] == "list":
            if isinstance(value, list):
                result[key] = [str(v).strip() for v in value if str(v).strip()]
            elif isinstance(value, str):
                result[key] = [v.strip() for v in value.replace("，", ",").split(",") if v.strip()]
            else:
                result[key] = []
        elif meta["type"] == "secret":
            result[key] = str(value or "")
        elif meta["type"] == "enum":
            result[key] = str(value) if str(value) in (meta.get("options") or []) else meta["default"]
        else:
            result[key] = str(value) if value else meta["default"]
    return result


def _backup_if_exists() -> None:
    if not SETTINGS_PATH.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"settings-{stamp}.yaml"
    dest.write_bytes(SETTINGS_PATH.read_bytes())


def saved_at() -> str:
    """ISO timestamp of settings.yaml mtime, or empty string."""
    try:
        mtime = SETTINGS_PATH.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
