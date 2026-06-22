"""Knowledge source connectors.

Connectors are deliberately small: they turn one configured knowledge base into
normalized text chunks. Retrieval and answer generation live elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

from ..configuration import KnowledgeBase
from .. import config

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SUPPORTED_LOCAL_EXTS = {".md", ".txt", ".json"}


@dataclass
class LoadedKnowledge:
    chunks: list[dict[str, Any]]
    signature: str


def _resolve_base_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _stable_id(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def _clean_text(text: str) -> str:
    lines = []
    last = ""
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line == last:
            continue
        lines.append(line)
        last = line
    return "\n".join(lines).strip()


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """Split plain text into stable chunks."""
    chunk_size = size or config.KNOWLEDGE_CHUNK_SIZE
    chunk_overlap = overlap if overlap is not None else config.KNOWLEDGE_CHUNK_OVERLAP
    cleaned = _clean_text(text)
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunk = cleaned[start:end]

        if end < len(cleaned):
            for sep in ["\n\n", "\n", "。", "；", "，", ". ", "; ", ", "]:
                pos = chunk.rfind(sep)
                if pos > chunk_size * 0.4:
                    chunk = chunk[:pos + len(sep)]
                    break

        chunk = chunk.strip()
        if len(chunk) >= 20:
            chunks.append(chunk)

        if not chunk:
            break
        start += max(len(chunk), chunk_size - chunk_overlap, 1)

    return chunks


def _metadata(kb: KnowledgeBase, source: str, provider: str, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "source": source,
        "kb_id": kb.id,
        "kb_name": kb.name,
        "kb_tags": kb.tags,
        "priority": kb.priority,
        "provider": provider,
    }
    data.update(extra)
    return data


def _make_chunks(
    kb: KnowledgeBase,
    text: str,
    source: str,
    provider: str,
    url: str = "",
    title: str = "",
) -> list[dict[str, Any]]:
    result = []
    for index, content in enumerate(chunk_text(text)):
        chunk_id = _stable_id(kb.id, provider, source, url, str(index), content[:80])
        result.append({
            "content": content,
            "chunk_id": chunk_id,
            **_metadata(kb, source, provider, url=url, title=title),
        })
    return result


def _signature(kb: KnowledgeBase, chunks: list[dict[str, Any]]) -> str:
    payload = {
        "kb": {
            "id": kb.id,
            "provider": kb.provider,
            "path": kb.path,
            "urls": kb.urls,
            "sitemap": kb.sitemap,
            "priority": kb.priority,
            "tags": kb.tags,
        },
        "chunk_size": config.KNOWLEDGE_CHUNK_SIZE,
        "chunk_overlap": config.KNOWLEDGE_CHUNK_OVERLAP,
        "embedding_model": config.EMBEDDING_MODEL,
        "chunks": [
            {
                "id": item.get("chunk_id"),
                "source": item.get("source"),
                "url": item.get("url", ""),
                "content_hash": _stable_id(item.get("content", "")),
            }
            for item in chunks
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


class LocalFilesConnector:
    provider = "local_files"

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def load(self) -> LoadedKnowledge:
        knowledge_dir = _resolve_base_path(self.kb.path)
        if not knowledge_dir.exists():
            logger.warning("知识库目录不存在: %s", knowledge_dir)
            return LoadedKnowledge([], _signature(self.kb, []))

        chunks: list[dict[str, Any]] = []
        for file in sorted(knowledge_dir.iterdir()):
            if not file.is_file() or file.suffix.lower() not in SUPPORTED_LOCAL_EXTS:
                continue
            try:
                chunks.extend(self._load_file(file))
            except Exception as exc:
                logger.warning("加载知识文件失败 %s: %s", file.name, exc)

        return LoadedKnowledge(chunks, _signature(self.kb, chunks))

    def _load_file(self, file: Path) -> list[dict[str, Any]]:
        content = file.read_text(encoding="utf-8")
        if file.suffix.lower() == ".json":
            return self._load_json(file.name, content)
        return _make_chunks(self.kb, content, file.name, self.provider)

    def _load_json(self, filename: str, content: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(content)
        except Exception as exc:
            logger.warning("解析 JSON 文件失败 %s: %s", filename, exc)
            return []

        if not isinstance(data, list):
            text = json.dumps(data, ensure_ascii=False, indent=2)
            return _make_chunks(self.kb, text, filename, self.provider)

        chunks: list[dict[str, Any]] = []
        for index, item in enumerate(data):
            if isinstance(item, dict) and ("question" in item or "answer" in item):
                text = f"问题：{item.get('question', '')}\n答案：{item.get('answer', '')}"
            else:
                text = json.dumps(item, ensure_ascii=False)
            source = f"{filename}#{index + 1}"
            chunks.extend(_make_chunks(self.kb, text, source, self.provider))
        return chunks


class WebConnector:
    provider = "web"

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def load(self) -> LoadedKnowledge:
        requests, BeautifulSoup = self._load_deps()
        urls = self._collect_urls(requests)
        chunks: list[dict[str, Any]] = []

        for url in urls[: config.WEB_MAX_PAGES_PER_KB]:
            try:
                chunks.extend(self._load_url(requests, BeautifulSoup, url))
            except Exception as exc:
                logger.warning("抓取网页失败 %s: %s", url, exc)

        return LoadedKnowledge(chunks, _signature(self.kb, chunks))

    def _load_deps(self):
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise RuntimeError("WebConnector 需要安装 requests 和 beautifulsoup4") from exc
        return requests, BeautifulSoup

    def _collect_urls(self, requests_module) -> list[str]:
        seen: set[str] = set()
        urls: list[str] = []

        def add(url: str):
            value = str(url or "").strip()
            if not value or not value.startswith(("http://", "https://")) or value in seen:
                return
            seen.add(value)
            urls.append(value)

        for url in self.kb.urls:
            add(url)

        sitemap = str(self.kb.sitemap or "").strip()
        if sitemap:
            try:
                response = requests_module.get(
                    sitemap,
                    headers={"User-Agent": config.WEB_USER_AGENT},
                    timeout=config.WEB_FETCH_TIMEOUT,
                )
                response.raise_for_status()
                for loc in self._parse_sitemap(response.text):
                    add(loc)
            except Exception as exc:
                logger.warning("读取 sitemap 失败 %s: %s", sitemap, exc)

        return urls

    @staticmethod
    def _parse_sitemap(xml_text: str) -> list[str]:
        root = ElementTree.fromstring(xml_text)
        result: list[str] = []
        for element in root.iter():
            if element.tag.endswith("loc") and element.text:
                result.append(element.text.strip())
        return result

    def _load_url(self, requests_module, BeautifulSoup, url: str) -> list[dict[str, Any]]:
        response = requests_module.get(
            url,
            headers={"User-Agent": config.WEB_USER_AGENT},
            timeout=config.WEB_FETCH_TIMEOUT,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()

        if "text/plain" in content_type:
            text = response.text
            title = self._title_from_url(url)
        elif "html" in content_type or not content_type:
            title, text = self._extract_html(BeautifulSoup, response.text, url)
        else:
            logger.info("跳过不支持的网页类型 %s: %s", content_type, url)
            return []

        source = title or self._title_from_url(url)
        return _make_chunks(self.kb, text, source, self.provider, url=url, title=title)

    @staticmethod
    def _extract_html(BeautifulSoup, html: str, url: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "form", "header", "footer", "nav"]):
            tag.decompose()

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            heading = soup.find(["h1", "h2"])
            title = heading.get_text(" ", strip=True) if heading else WebConnector._title_from_url(url)

        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = main.get_text("\n", strip=True)
        return title, text

    @staticmethod
    def _title_from_url(url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/").split("/")[-1]
        return path or parsed.netloc or url


def create_connector(kb: KnowledgeBase):
    provider = kb.provider or "local_files"
    if provider == "local_files":
        return LocalFilesConnector(kb)
    if provider == "web":
        return WebConnector(kb)
    raise ValueError(f"不支持的知识库 provider: {provider}")


def load_knowledge(kb: KnowledgeBase) -> LoadedKnowledge:
    connector = create_connector(kb)
    return connector.load()
