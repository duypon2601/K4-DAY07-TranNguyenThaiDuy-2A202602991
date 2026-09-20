from __future__ import annotations

from typing import Any, Callable

from .chunking import compute_similarity
from .embeddings import _mock_embed
from .models import Document


class EmbeddingStore:
    """
    A vector store for text chunks.

    Uses an efficient in-memory store with cosine similarity retrieval.
    The embedding_fn parameter allows injection of mock or real embeddings.
    """

    def __init__(
        self,
        collection_name: str = "documents",
        embedding_fn: Callable[[str], list[float]] | None = None,
    ) -> None:
        self._embedding_fn = embedding_fn or _mock_embed
        self._collection_name = collection_name
        self._use_chroma = False
        self._store: list[dict[str, Any]] = []

    def _make_record(self, doc: Document) -> dict[str, Any]:
        meta = dict(doc.metadata) if doc.metadata is not None else {}
        if "doc_id" not in meta:
            meta["doc_id"] = doc.id.split("#")[0] if doc.id else ""
        embedding = self._embedding_fn(doc.content)
        return {
            "id": doc.id,
            "content": doc.content,
            "metadata": meta,
            "embedding": embedding,
        }

    def _search_records(self, query: str, records: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        if not records or top_k <= 0:
            return []
        query_vec = self._embedding_fn(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for rec in records:
            score = compute_similarity(query_vec, rec["embedding"])
            scored.append((score, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, rec in scored[:top_k]:
            results.append({
                "id": rec["id"],
                "content": rec["content"],
                "metadata": rec["metadata"],
                "score": score,
            })
        return results

    def add_documents(self, docs: list[Document]) -> None:
        """Embed each document's content and append to in-memory store."""
        for doc in docs:
            record = self._make_record(doc)
            self._store.append(record)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Find the top_k most similar documents to query."""
        return self._search_records(query, self._store, top_k)

    def get_collection_size(self) -> int:
        """Return the total number of stored chunks."""
        return len(self._store)

    def search_with_filter(self, query: str, top_k: int = 3, metadata_filter: dict | None = None) -> list[dict]:
        """
        Search with metadata pre-filtering.

        First filter stored chunks by metadata_filter, then run similarity search on matching candidates.
        """
        if not metadata_filter:
            return self._search_records(query, self._store, top_k)

        candidates = [
            rec for rec in self._store
            if all(rec["metadata"].get(k) == v for k, v in metadata_filter.items())
        ]
        return self._search_records(query, candidates, top_k)

    def delete_document(self, doc_id: str) -> bool:
        """
        Remove all chunks belonging to a document.

        Returns True if any chunks were removed, False otherwise.
        """
        initial_count = len(self._store)
        self._store = [
            rec for rec in self._store
            if rec["metadata"].get("doc_id") != doc_id and rec["id"] != doc_id
        ]
        return len(self._store) < initial_count
