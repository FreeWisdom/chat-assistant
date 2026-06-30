"""Provider factory — create knowledge clients and managers by provider name."""

from __future__ import annotations

from .provider_protocol import KnowledgeClientProtocol, KnowledgeManagerProtocol


def create_knowledge_client(provider: str) -> KnowledgeClientProtocol:
    if provider == "maxkb":
        from .maxkb_knowledge import MaxKBKnowledgeClient

        return MaxKBKnowledgeClient()

    raise ValueError(f"不支持的知识库 provider: {provider}")


def create_knowledge_manager(provider: str):  # → KnowledgeManagerProtocol
    if provider == "maxkb":
        from .maxkb_knowledge import MaxKBKnowledgeManager

        return MaxKBKnowledgeManager()

    raise ValueError(f"不支持的知识库 provider: {provider}")
