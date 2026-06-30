"""Admin config persistence for the local management page."""
from __future__ import annotations

from datetime import datetime
import logging
import re
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "bot.yaml"
BACKUP_DIR = PROJECT_ROOT / "runtime" / "backups"
SUPPORTED_PROVIDERS = {"maxkb"}
INTERNAL_KNOWLEDGE_FIELDS = set()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_config()
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or _empty_config()


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=120)


def _empty_config() -> dict[str, Any]:
    return {
        "botProfiles": [],
        "styles": [],
        "knowledgeBases": [],
        "bindings": [],
        "global": {
            "excludeGroups": [],
            "admins": [],
            "cooldownSeconds": 30,
            "smartDetection": True,
        },
    }


def _listify(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _configured_value(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.startswith("your-") else text


def _ensure_unique_ids(items: list[dict[str, Any]], section: str) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            errors.append(f"{section}[{index}] 缺少 id")
            continue
        if item_id in seen:
            errors.append(f"{section} 存在重复 id: {item_id}")
        seen.add(item_id)
    return errors


def normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    normalized = _empty_config()

    normalized["styles"] = []
    for item in _listify(data.get("styles")):
        style_id = str(item.get("id", "")).strip()
        normalized["styles"].append({
            "id": style_id,
            "name": str(item.get("name", "")).strip(),
            "tone": str(item.get("tone", "")).strip(),
            "maxChars": int(item.get("maxChars") or 200),
            "emojiPolicy": str(item.get("emojiPolicy", "")).strip() or "少用",
            "avoidWords": [str(v).strip() for v in _listify(item.get("avoidWords")) if str(v).strip()],
            "examples": [
                {
                    "user": str(ex.get("user", "")).strip(),
                    "assistant": str(ex.get("assistant", "")).strip(),
                }
                for ex in _listify(item.get("examples"))
                if isinstance(ex, dict) and (str(ex.get("user", "")).strip() or str(ex.get("assistant", "")).strip())
            ],
        })

    normalized["botProfiles"] = []
    for item in _listify(data.get("botProfiles")):
        normalized["botProfiles"].append({
            "id": str(item.get("id", "")).strip(),
            "name": str(item.get("name", "")).strip(),
            "role": str(item.get("role", "")).strip(),
            "styleId": str(item.get("styleId", "")).strip(),
            "answerPolicyId": str(item.get("answerPolicyId", "")).strip() or "strict-kb",
            "responsibilities": [str(v).strip() for v in _listify(item.get("responsibilities")) if str(v).strip()],
            "identityPrompt": str(item.get("identityPrompt", "")).strip(),
        })

    normalized["knowledgeBases"] = []
    for item in _listify(data.get("knowledgeBases")):
        kb_id = str(item.get("id", "")).strip()
        provider = (
            str(item.get("provider", "maxkb")).strip()
            or "maxkb"
        )
        normalized["knowledgeBases"].append({
            "id": kb_id,
            "name": str(item.get("name", "")).strip(),
            "description": str(item.get("description", "")).strip(),
            "provider": provider,

            "maxkbAppId": str(item.get("maxkbAppId", "") or "").strip(),
            "tags": [str(v).strip() for v in _listify(item.get("tags")) if str(v).strip()],
            "priority": int(item.get("priority") or 0),
            "fallbackPolicy": str(item.get("fallbackPolicy", "")).strip() or "clarify",
            "routeExamples": [str(v).strip() for v in _listify(item.get("routeExamples")) if str(v).strip()],
        })

    normalized["bindings"] = []
    for item in _listify(data.get("bindings")):
        normalized["bindings"].append({
            "group": str(item.get("group", "")).strip(),
            "botId": str(item.get("botId", "")).strip(),
            "knowledgeBaseIds": [
                str(v).strip()
                for v in _listify(item.get("knowledgeBaseIds"))
                if str(v).strip()
            ],
            "replyTriggers": [
                str(v).strip()
                for v in _listify(item.get("replyTriggers"))
                if str(v).strip()
            ],
        })

    global_cfg = data.get("global") or {}
    normalized["global"] = {
        "excludeGroups": [str(v).strip() for v in _listify(global_cfg.get("excludeGroups")) if str(v).strip()],
        "admins": [str(v).strip() for v in _listify(global_cfg.get("admins")) if str(v).strip()],
        "cooldownSeconds": int(global_cfg.get("cooldownSeconds") or 30),
        "smartDetection": bool(global_cfg.get("smartDetection", True)),
    }

    return normalized


def validate_config(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_ensure_unique_ids(data.get("botProfiles", []), "botProfiles"))
    errors.extend(_ensure_unique_ids(data.get("styles", []), "styles"))
    errors.extend(_ensure_unique_ids(data.get("knowledgeBases", []), "knowledgeBases"))

    style_ids = {item["id"] for item in data.get("styles", []) if item.get("id")}
    bot_ids = {item["id"] for item in data.get("botProfiles", []) if item.get("id")}
    kb_ids = {item["id"] for item in data.get("knowledgeBases", []) if item.get("id")}
    groups: set[str] = set()

    for bot in data.get("botProfiles", []):
        if not bot.get("name"):
            errors.append(f"机器人 {bot.get('id') or '<unknown>'} 缺少名称")
        if bot.get("styleId") not in style_ids:
            errors.append(f"机器人 {bot.get('id')} 绑定的 styleId 不存在: {bot.get('styleId')}")

    for style in data.get("styles", []):
        if int(style.get("maxChars") or 0) <= 0:
            errors.append(f"风格 {style.get('id')} 的 maxChars 必须大于 0")

    bound_kb_ids = {
        str(kb_id).strip()
        for binding in data.get("bindings", [])
        for kb_id in binding.get("knowledgeBaseIds", [])
        if str(kb_id).strip()
    }

    from . import config as app_config

    for kb in data.get("knowledgeBases", []):
        kb_id = kb.get("id") or "<unknown>"
        if not kb.get("name"):
            errors.append(f"知识库 {kb_id} 缺少名称")
        provider = kb.get("provider") or "maxkb"
        if provider not in SUPPORTED_PROVIDERS:
            errors.append(f"知识库 {kb_id} 的 provider 不支持: {provider}")
            continue
        if kb.get("id") in bound_kb_ids and not _configured_value(kb.get("maxkbAppId")):
            errors.append(f"MaxKB 知识库 {kb_id} 缺少 maxkbAppId")

    for index, binding in enumerate(data.get("bindings", [])):
        group = str(binding.get("group", "")).strip()
        if not group:
            errors.append(f"bindings[{index}] 缺少微信群名")
        elif group in groups:
            errors.append(f"微信群重复绑定: {group}")
        groups.add(group)

        if binding.get("botId") not in bot_ids:
            errors.append(f"群 {group or index} 绑定的 botId 不存在: {binding.get('botId')}")
        for kb_id in binding.get("knowledgeBaseIds", []):
            if kb_id not in kb_ids:
                errors.append(f"群 {group or index} 绑定的 knowledgeBaseId 不存在: {kb_id}")

    return errors


def read_config() -> dict[str, Any]:
    return normalize_config(_load_yaml(CONFIG_PATH))


def public_config(data: dict[str, Any]) -> dict[str, Any]:
    """Return browser-safe config without cloud vendor identifiers."""
    normalized = normalize_config(data)
    result = {
        key: value
        for key, value in normalized.items()
        if key != "knowledgeBases"
    }
    result["knowledgeBases"] = []
    for item in normalized.get("knowledgeBases", []):
        public_item = {
            key: value
            for key, value in item.items()
            if key not in INTERNAL_KNOWLEDGE_FIELDS
        }
        public_item["configured"] = bool(_configured_value(item.get("maxkbAppId")))
        public_item["providerLabel"] = "MaxKB"
        result["knowledgeBases"].append(public_item)
    return result


def merge_public_config(
    payload: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    """Restore server-only knowledge fields before validating and saving."""
    from . import config

    existing_by_id = {
        item.get("id"): item
        for item in existing.get("knowledgeBases", [])
        if item.get("id")
    }
    merged = {
        **payload,
        "knowledgeBases": [],
    }
    for item in _listify(payload.get("knowledgeBases")):
        kb_id = str(item.get("id", "")).strip()
        current = existing_by_id.get(kb_id, {})
        merged["knowledgeBases"].append({
            **item,
            "provider": (
                current.get("provider")
                if kb_id in existing_by_id
                else item.get("provider", "maxkb")
            ),
            "maxkbAppId": (
                item.get("maxkbAppId", "")
                if "maxkbAppId" in item
                else current.get("maxkbAppId", "")
            ),
        })
    return merged


def write_config(
    data: dict[str, Any],
    *,
    create_backup: bool = True,
) -> dict[str, Any]:
    normalized = normalize_config(data)
    errors = validate_config(normalized)
    if errors:
        raise ValueError("\n".join(errors))

    if create_backup and CONFIG_PATH.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(CONFIG_PATH, BACKUP_DIR / f"courses-{stamp}.yaml")

    _dump_yaml(CONFIG_PATH, normalized)
    return normalized


def upsert_knowledge_base(item: dict[str, Any]) -> dict[str, Any]:
    """Persist one cloud knowledge base while preserving the rest of config."""
    kb_id = str(item.get("id", "")).strip()
    if not kb_id:
        raise ValueError("知识库 ID 不能为空")

    config_data = read_config()
    knowledge_bases = config_data.get("knowledgeBases", [])
    existing_index = next(
        (
            index
            for index, knowledge_base in enumerate(knowledge_bases)
            if knowledge_base.get("id") == kb_id
        ),
        None,
    )
    if existing_index is None:
        knowledge_bases.append(item)
    else:
        knowledge_bases[existing_index] = {
            **knowledge_bases[existing_index],
            **item,
        }
    config_data["knowledgeBases"] = knowledge_bases
    return write_config(config_data)


def update_knowledge_job_status(
    kb_id: str,
    status: str,
) -> dict[str, Any]:
    return update_knowledge_cloud_state(
        kb_id,
        index_status=status,
    )


def update_knowledge_cloud_state(
    kb_id: str,
    *,
    index_job_id: str | None = None,
    index_status: str | None = None,
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    config_data = read_config()
    knowledge_base = next(
        (
            item
            for item in config_data.get("knowledgeBases", [])
            if item.get("id") == kb_id
        ),
        None,
    )
    if knowledge_base is None:
        raise ValueError(f"知识库不存在: {kb_id}")
    if index_job_id is not None:
        knowledge_base["indexJobId"] = str(index_job_id or "").strip()
    if index_status is not None:
        knowledge_base["indexStatus"] = str(index_status or "").strip()
    if document_ids is not None:
        knowledge_base["documentIds"] = list(dict.fromkeys(
            str(item).strip()
            for item in document_ids
            if str(item).strip()
        ))
    return write_config(config_data, create_backup=False)


def _file_info(file: Path) -> dict[str, Any]:
    stat = file.stat()
    return {
        "name": file.name,
        "size": stat.st_size,
        "path": "./" + file.relative_to(PROJECT_ROOT).as_posix(),
        "modifiedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _backup_file_info(file: Path) -> dict[str, Any]:
    info = _file_info(file)
    match = re.match(r"courses-(\d{8})-(\d{6})\.yaml$", file.name)
    if match:
        timestamp = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
        info["modifiedAt"] = timestamp.isoformat(timespec="seconds")
    return info


def list_backups(limit: int = 12) -> list[dict[str, Any]]:
    if not BACKUP_DIR.exists():
        return []
    backups = [
        _backup_file_info(file)
        for file in BACKUP_DIR.glob("courses-*.yaml")
        if file.is_file()
    ]
    backups.sort(key=lambda item: item["modifiedAt"], reverse=True)
    return backups[:limit]
