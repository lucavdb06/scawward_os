"""
MemoryEngine — short-term + long-term memory.

Three layers:
  1. Working memory:   conversation history (in-process, capped).
  2. Episodic memory:  every executed action/outcome (SQL).
  3. Semantic memory:  embeddings of important facts (Chroma).

The agent calls `recall(query)` before responding to fetch relevant
prior experience. After every interaction we call `remember(...)` to
persist what mattered.

NOTE: SQL access is delegated to db.repositories so this file stays
focused on policy (what to remember, what to recall).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class MemoryItem:
    id: str
    kind: str              # "fact" | "preference" | "action" | "observation"
    content: str
    metadata: dict[str, Any]
    score: float = 0.0     # similarity if from semantic recall


class VectorStore(Protocol):
    async def upsert(self, doc_id: str, text: str,
                     metadata: dict[str, Any]) -> None: ...
    async def query(self, text: str, k: int = 5,
                    where: dict[str, Any] | None = None) -> list[MemoryItem]: ...


class EpisodicStore(Protocol):
    async def log(self, kind: str, content: str,
                  metadata: dict[str, Any]) -> str: ...
    async def recent(self, n: int = 20) -> list[MemoryItem]: ...


class MemoryEngine:
    def __init__(self, vector: VectorStore, episodic: EpisodicStore) -> None:
        self.vector = vector
        self.episodic = episodic
        self._working: list[dict[str, Any]] = []      # chat-style turns
        self._working_max = 40

    # ─── Working memory (conversation) ────────────────────────────
    def append_turn(self, role: str, content: str | list[Any]) -> None:
        self._working.append({"role": role, "content": content})
        if len(self._working) > self._working_max:
            # Keep first system + last N
            self._working = self._working[-self._working_max :]

    def working_memory(self) -> list[dict[str, Any]]:
        return list(self._working)

    def reset_working(self) -> None:
        self._working.clear()

    # ─── Long-term: write ─────────────────────────────────────────
    async def remember(self, kind: str, content: str,
                       metadata: dict[str, Any] | None = None,
                       semantic: bool = True) -> str:
        meta = metadata or {}
        meta["kind"] = kind
        doc_id = await self.episodic.log(kind, content, meta)
        if semantic and self._is_worth_embedding(kind, content):
            await self.vector.upsert(doc_id, content, meta)
        return doc_id

    # ─── Long-term: read ──────────────────────────────────────────
    async def recall(self, query: str, k: int = 5,
                     kinds: list[str] | None = None) -> list[MemoryItem]:
        where = {"kind": {"$in": kinds}} if kinds else None
        try:
            return await self.vector.query(query, k=k, where=where)
        except Exception:
            logger.exception("vector recall failed; returning empty")
            return []

    async def recent_actions(self, n: int = 10) -> list[MemoryItem]:
        items = await self.episodic.recent(n=n * 2)
        return [m for m in items if m.kind == "action"][:n]

    # ─── Heuristics ───────────────────────────────────────────────
    @staticmethod
    def _is_worth_embedding(kind: str, content: str) -> bool:
        """Don't waste embeddings on noise."""
        if len(content.strip()) < 12:
            return False
        if kind in {"fact", "preference", "observation"}:
            return True
        if kind == "action" and len(content) > 60:
            return True
        return False
