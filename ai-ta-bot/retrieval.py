"""Retriever implementations for local and indexed knowledge search."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
import json
import logging
import re

from course_manager import KnowledgeBase
from knowledge_connectors import load_knowledge
import config

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


def _resolve_runtime_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate.resolve()


def _extract_terms(text: str) -> list[str]:
    """Small Chinese/English term extractor for keyword search."""
    cleaned = re.sub(r"[，。？！、；：\"'（）【】《》\s\n\r]", " ", text)
    terms: list[str] = []

    for match in re.finditer(r"[a-zA-Z_]\w{2,}", cleaned):
        terms.append(match.group().lower())

    for match in re.finditer(r"[\u4e00-\u9fff]{2,8}", cleaned):
        chunk = match.group()
        terms.append(chunk)
        if len(chunk) >= 4:
            for i in range(len(chunk) - 1):
                terms.append(chunk[i:i + 2])

    return list(dict.fromkeys(terms))


def _metadata_for_chroma(doc: dict[str, Any]) -> dict[str, Any]:
    tags = doc.get("kb_tags") or []
    return {
        "kb_id": str(doc.get("kb_id", "")),
        "kb_name": str(doc.get("kb_name", "")),
        "kb_tags": ",".join(str(tag) for tag in tags),
        "source": str(doc.get("source", "")),
        "provider": str(doc.get("provider", "")),
        "url": str(doc.get("url", "")),
        "title": str(doc.get("title", "")),
        "priority": int(doc.get("priority", 0) or 0),
        "chunk_id": str(doc.get("chunk_id", "")),
    }


def _doc_from_chroma(content: str, metadata: dict[str, Any]) -> dict[str, Any]:
    tags = [
        item.strip()
        for item in str(metadata.get("kb_tags", "")).split(",")
        if item.strip()
    ]
    return {
        "content": content,
        "chunk_id": metadata.get("chunk_id") or "",
        "source": metadata.get("source") or "",
        "kb_id": metadata.get("kb_id") or "",
        "kb_name": metadata.get("kb_name") or "",
        "kb_tags": tags,
        "priority": int(metadata.get("priority", 0) or 0),
        "provider": metadata.get("provider") or "",
        "url": metadata.get("url") or "",
        "title": metadata.get("title") or "",
    }


class KeywordRetriever:
    """In-memory keyword retriever kept as the reliable exact-match layer."""

    def __init__(self):
        self.docs: dict[str, list[dict[str, Any]]] = {}

    def load_knowledge_base(self, kb_id: str, docs: list[dict[str, Any]]) -> None:
        self.docs[kb_id] = docs

    def search(self, knowledge_base_ids: list[str], query: str, top_k: int) -> list[dict[str, Any]]:
        documents = []
        for kb_id in knowledge_base_ids:
            documents.extend(self.docs.get(kb_id, []))
        if not documents:
            return []

        query_terms = _extract_terms(query)
        if not query_terms:
            return documents[:top_k]

        scored: list[tuple[float, dict[str, Any]]] = []
        for doc in documents:
            score = float(doc.get("priority", 0) or 0)
            content = str(doc.get("content", ""))
            tag_text = " ".join(str(tag) for tag in doc.get("kb_tags", []))
            source_text = f"{doc.get('source', '')} {doc.get('title', '')}"

            for term in query_terms:
                count = content.lower().count(term.lower())
                if count > 0:
                    score += len(term) * count
                if term in tag_text:
                    score += len(term) * 2
                if term.lower() in source_text.lower():
                    score += len(term) * 1.5

            for line in content.split("\n"):
                if line.startswith("#"):
                    for term in query_terms:
                        if term in line:
                            score += len(term) * 3

            if score > 0:
                item = dict(doc)
                item["_keyword_score"] = score
                scored.append((score, item))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]


class ChromaVectorIndex:
    """Persistent local vector index using Chroma when dependencies exist."""

    def __init__(self):
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        self.db_dir = _resolve_runtime_path(config.VECTOR_DB_DIR)
        self.manifest_path = _resolve_runtime_path(config.INDEX_MANIFEST_PATH)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        self.embedding_function = SentenceTransformerEmbeddingFunction(
            model_name=config.EMBEDDING_MODEL,
            device=config.EMBEDDING_DEVICE,
        )
        self.client = chromadb.PersistentClient(path=str(self.db_dir))
        self.collection = self.client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_NAME,
            embedding_function=self.embedding_function,
        )
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"knowledge_bases": {}}
        try:
            with self.manifest_path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            logger.warning("索引 manifest 损坏，将重新生成: %s", self.manifest_path)
            return {"knowledge_bases": {}}

    def _save_manifest(self) -> None:
        with self.manifest_path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(self.manifest, file, ensure_ascii=False, indent=2, sort_keys=True)

    def ensure_knowledge_base(self, kb: KnowledgeBase, docs: list[dict[str, Any]], signature: str) -> None:
        existing = self.manifest.get("knowledge_bases", {}).get(kb.id)
        if existing and existing.get("signature") == signature and existing.get("chunk_count") == len(docs):
            logger.info("向量索引未变化，跳过重建: %s", kb.name)
            return

        logger.info("重建向量索引: %s (%s chunks)", kb.name, len(docs))
        try:
            self.collection.delete(where={"kb_id": kb.id})
        except Exception as exc:
            logger.debug("删除旧向量索引时可忽略的异常 %s: %s", kb.id, exc)

        batch_size = config.CHROMA_BATCH_SIZE
        for start in range(0, len(docs), batch_size):
            batch = docs[start:start + batch_size]
            if not batch:
                continue
            self.collection.add(
                ids=[str(doc.get("chunk_id")) for doc in batch],
                documents=[str(doc.get("content", "")) for doc in batch],
                metadatas=[_metadata_for_chroma(doc) for doc in batch],
            )

        self.manifest.setdefault("knowledge_bases", {})[kb.id] = {
            "signature": signature,
            "chunk_count": len(docs),
            "provider": kb.provider,
            "embedding_model": config.EMBEDDING_MODEL,
        }
        self._save_manifest()

    def search(self, knowledge_base_ids: list[str], query: str, top_k: int) -> list[dict[str, Any]]:
        if not knowledge_base_ids:
            return []

        results: list[dict[str, Any]] = []
        for kb_id in knowledge_base_ids:
            try:
                payload = self.collection.query(
                    query_texts=[query],
                    n_results=top_k,
                    where={"kb_id": kb_id},
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as exc:
                logger.warning("向量检索失败 %s: %s", kb_id, exc)
                continue

            documents = (payload.get("documents") or [[]])[0]
            metadatas = (payload.get("metadatas") or [[]])[0]
            distances = (payload.get("distances") or [[]])[0]

            for content, metadata, distance in zip(documents, metadatas, distances):
                if not content or not metadata:
                    continue
                doc = _doc_from_chroma(content, metadata)
                doc["_vector_distance"] = float(distance) if distance is not None else 1.0
                doc["_vector_score"] = 1.0 / (1.0 + doc["_vector_distance"])
                results.append(doc)

        results.sort(key=lambda item: item.get("_vector_distance", 1e9))
        return results[:top_k]


class HybridRetriever:
    """Keyword + optional Chroma vector retrieval."""

    def __init__(self):
        self.keyword = KeywordRetriever()
        self.vector: ChromaVectorIndex | None = None
        if config.VECTOR_SEARCH_ENABLED:
            try:
                self.vector = ChromaVectorIndex()
                logger.info("Chroma 向量检索已启用: %s", config.VECTOR_DB_DIR)
            except Exception as exc:
                logger.warning("Chroma 向量检索不可用，将只使用关键词检索: %s", exc)

    def load_knowledge_base(self, kb: KnowledgeBase) -> int:
        try:
            loaded = load_knowledge(kb)
        except Exception as exc:
            logger.error("加载知识库失败 %s: %s", kb.name, exc)
            self.keyword.load_knowledge_base(kb.id, [])
            return 0

        self.keyword.load_knowledge_base(kb.id, loaded.chunks)
        if self.vector:
            try:
                self.vector.ensure_knowledge_base(kb, loaded.chunks, loaded.signature)
            except Exception as exc:
                logger.warning("知识库向量索引失败 %s，将保留关键词检索: %s", kb.name, exc)

        logger.info("知识库 %s 已加载: %s 个文档块", kb.name, len(loaded.chunks))
        return len(loaded.chunks)

    def search(self, knowledge_base_ids: list[str], query: str, top_k: int = 5) -> list[dict[str, Any]]:
        keyword_results = self.keyword.search(knowledge_base_ids, query, top_k=max(top_k * 2, 6))
        vector_results = self.vector.search(knowledge_base_ids, query, top_k=max(top_k * 2, 6)) if self.vector else []

        combined: dict[str, dict[str, Any]] = {}
        scores: defaultdict[str, float] = defaultdict(float)

        for rank, doc in enumerate(keyword_results):
            key = str(doc.get("chunk_id") or f"keyword-{rank}")
            combined[key] = doc
            scores[key] += 1.0 / (rank + 1)
            scores[key] += min(float(doc.get("_keyword_score", 0) or 0) / 40.0, 1.0)

        for rank, doc in enumerate(vector_results):
            key = str(doc.get("chunk_id") or f"vector-{rank}")
            if key not in combined:
                combined[key] = doc
            else:
                combined[key].update({k: v for k, v in doc.items() if k.startswith("_vector")})
            scores[key] += 1.6 / (rank + 1)
            scores[key] += float(doc.get("_vector_score", 0) or 0)

        ranked = []
        for key, doc in combined.items():
            item = dict(doc)
            item["_score"] = scores[key]
            ranked.append(item)
        ranked.sort(key=lambda item: item.get("_score", 0), reverse=True)
        return ranked[:top_k]
