"""
ChromaDB-backed VectorStore.

Why Chroma?
  - Embedded (no extra service for solo dev)
  - Built-in default embedder (no API call needed for MVP)
  - Easy to swap for pgvector / Qdrant later
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..core.memory_engine import MemoryItem, VectorStore

logger = logging.getLogger(__name__)


class ChromaVectorStore(VectorStore):
    def __init__(self, collection_name: str = "scawward_memory") -> None:
        import chromadb
        cfg = get_settings()
        Path(cfg.vector_db_path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=cfg.vector_db_path)
        self._col = self._client.get_or_create_collection(collection_name)

    async def upsert(self, doc_id: str, text: str,
                     metadata: dict[str, Any]) -> None:
        # Chroma is sync; we accept the small blocking cost in solo MVP.
        try:
            self._col.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[self._sanitize_meta(metadata)],
            )
        except Exception:
            logger.exception("chroma upsert failed for %s", doc_id)

    async def query(self, text: str, k: int = 5,
                    where: dict[str, Any] | None = None) -> list[MemoryItem]:
        try:
            res = self._col.query(query_texts=[text], n_results=k, where=where)
        except Exception:
            logger.exception("chroma query failed for %r", text[:60])
            return []

        items: list[MemoryItem] = []
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for i, (doc_id, doc, meta, dist) in enumerate(zip(ids, docs, metas, dists)):
            items.append(MemoryItem(
                id=doc_id,
                kind=(meta or {}).get("kind", "fact"),
                content=doc,
                metadata=meta or {},
                score=1.0 - float(dist),       # cosine-ish
            ))
        return items

    @staticmethod
    def _sanitize_meta(meta: dict[str, Any]) -> dict[str, Any]:
        # Chroma metadata must be primitive scalars.
        out: dict[str, Any] = {}
        for k, v in meta.items():
            if isinstance(v, (str, int, float, bool)):
                out[k] = v
            else:
                out[k] = str(v)
        return out
