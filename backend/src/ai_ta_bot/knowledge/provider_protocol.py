"""Provider-agnostic knowledge client and manager interfaces.

AliyunBailianKnowledgeClient already satisfies KnowledgeClientProtocol
structurally — no ABC inheritance required.
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict


class KnowledgeSearchResult(TypedDict, total=False):
    """Normalised chunk returned by any knowledge provider.

    Adapter layer maps provider-specific fields to these protocol fields
    so RAGEngine consumes one shape regardless of provider.
    """

    title: str
    content: str
    source_name: str
    url: str
    score: float
    knowledge_base_id: str
    metadata: dict[str, Any]


class KnowledgeClientProtocol(Protocol):
    """Structural interface for query-time knowledge retrieval."""

    provider: str

    def validate(self, knowledge_bases: list[Any]) -> None:
        """Raise ValueError if any KB is incompatible with this client."""
        ...

    def search(
        self,
        knowledge_bases: list[Any],
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return normalised chunks (at least content / score / source_name)."""
        ...


class KnowledgeManagerProtocol(Protocol):
    """Structural interface for admin-time knowledge provisioning."""

    def provision(
        self,
        *,
        workspace_id: str = "",
        name: str = "",
        description: str = "",
        uploads: list[Any] | None = None,
        tags: list[str] | None = None,
        index_id: str = "",
    ) -> Any:
        ...

    def get_job_status(self, *, workspace_id: str, index_id: str, job_id: str) -> Any:
        ...

    def list_cloud_documents(self, *, workspace_id: str, index_id: str) -> list[dict[str, Any]]:
        ...

    def delete_document(self, *, workspace_id: str, index_id: str, file_id: str) -> bool:
        ...
