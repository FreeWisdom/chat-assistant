"""Admin config persistence for the local management page."""
from __future__ import annotations

from datetime import datetime
import re
import shutil
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "bot.yaml"
BACKUP_DIR = PROJECT_ROOT / "runtime" / "backups"
KNOWLEDGE_DATA_DIR = PROJECT_ROOT / "knowledge-data"
SUPPORTED_KNOWLEDGE_EXTS = {".md", ".txt", ".json"}
SUPPORTED_PROVIDERS = {"local_files", "web"}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")
    return cleaned.lower() or "knowledge-base"


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


def _safe_knowledge_path(raw_path: str, kb_id: str) -> str:
    path_text = raw_path.strip() if raw_path else f"knowledge-data/{_slug(kb_id)}"
    candidate = (PROJECT_ROOT / path_text).resolve()
    try:
        candidate.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"知识库路径必须位于项目目录下: {path_text}") from exc
    return "./" + candidate.relative_to(PROJECT_ROOT).as_posix()


def _clean_urls(value: Any) -> list[str]:
    return [
        str(item).strip()
        for item in _listify(value)
        if str(item).strip()
    ]


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
        provider = str(item.get("provider", "local_files")).strip() or "local_files"
        path = ""
        if provider == "local_files":
            path = _safe_knowledge_path(str(item.get("path", "")).strip(), kb_id)
        else:
            path = str(item.get("path", "")).strip()
        normalized["knowledgeBases"].append({
            "id": kb_id,
            "name": str(item.get("name", "")).strip(),
            "description": str(item.get("description", "")).strip(),
            "provider": provider,
            "path": path,
            "urls": _clean_urls(item.get("urls")),
            "sitemap": str(item.get("sitemap", "")).strip(),
            "credential": str(item.get("credential", "")).strip(),
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

    for kb in data.get("knowledgeBases", []):
        if not kb.get("name"):
            errors.append(f"知识库 {kb.get('id') or '<unknown>'} 缺少名称")
        provider = kb.get("provider") or "local_files"
        if provider not in SUPPORTED_PROVIDERS:
            errors.append(f"知识库 {kb.get('id') or '<unknown>'} 的 provider 不支持: {provider}")
            continue
        if provider == "local_files":
            try:
                _safe_knowledge_path(str(kb.get("path", "")), str(kb.get("id", "")))
            except ValueError as exc:
                errors.append(str(exc))
        if provider == "web":
            urls = _clean_urls(kb.get("urls"))
            sitemap = str(kb.get("sitemap", "")).strip()
            if not urls and not sitemap:
                errors.append(f"网页知识库 {kb.get('id') or '<unknown>'} 至少需要填写一个 URL 或 sitemap")
            for url in [*urls, sitemap]:
                if url and not url.startswith(("http://", "https://")):
                    errors.append(f"网页知识库 {kb.get('id') or '<unknown>'} 地址必须以 http:// 或 https:// 开头: {url}")

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


def write_config(data: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_config(data)
    errors = validate_config(normalized)
    if errors:
        raise ValueError("\n".join(errors))

    if CONFIG_PATH.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(CONFIG_PATH, BACKUP_DIR / f"courses-{stamp}.yaml")

    for kb in normalized.get("knowledgeBases", []):
        if kb.get("provider", "local_files") != "local_files":
            continue
        (PROJECT_ROOT / kb["path"]).mkdir(parents=True, exist_ok=True)

    _dump_yaml(CONFIG_PATH, normalized)
    return normalized


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


def list_knowledge_files(kb_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    config_data = read_config()
    result: dict[str, list[dict[str, Any]]] = {}
    for kb in config_data.get("knowledgeBases", []):
        if kb_id and kb["id"] != kb_id:
            continue
        if kb.get("provider", "local_files") != "local_files":
            result[kb["id"]] = []
            continue
        kb_dir = (PROJECT_ROOT / kb["path"]).resolve()
        files: list[dict[str, Any]] = []
        if kb_dir.exists():
            for file in sorted(kb_dir.iterdir()):
                if file.is_file() and file.suffix.lower() in SUPPORTED_KNOWLEDGE_EXTS:
                    files.append(_file_info(file))
        result[kb["id"]] = files
    return result


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


def save_knowledge_file(kb_id: str, filename: str, content: bytes) -> dict[str, Any]:
    config_data = read_config()
    kb = next((item for item in config_data.get("knowledgeBases", []) if item["id"] == kb_id), None)
    if not kb:
        raise ValueError(f"知识库不存在: {kb_id}")
    if kb.get("provider", "local_files") != "local_files":
        raise ValueError("只有本地文件知识库支持上传文件")

    safe_name = Path(filename).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_KNOWLEDGE_EXTS:
        raise ValueError(f"不支持的文件类型: {suffix or '<none>'}")
    if not content:
        raise ValueError("上传文件为空")

    kb_dir = (PROJECT_ROOT / kb["path"]).resolve()
    kb_dir.mkdir(parents=True, exist_ok=True)
    target = kb_dir / safe_name
    target.write_bytes(content)
    return _file_info(target)
