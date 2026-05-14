"""
Repository layer — concrete implementations of the protocols required
by `core.memory_engine`.

Keeps SQL & vector code out of the engine itself.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import desc, select

from ..core.memory_engine import EpisodicStore, MemoryItem as MemoryItemDTO
from .models import MemoryItem
from .session import get_session

logger = logging.getLogger(__name__)


class SqlEpisodicStore(EpisodicStore):
    async def log(self, kind: str, content: str,
                  metadata: dict[str, Any]) -> str:
        async with get_session() as s:
            item = MemoryItem(kind=kind, content=content, meta=metadata)
            s.add(item)
            await s.flush()
            return item.id

    async def recent(self, n: int = 20) -> list[MemoryItemDTO]:
        async with get_session() as s:
            rows = (
                await s.execute(select(MemoryItem).order_by(desc(MemoryItem.created_at)).limit(n))
            ).scalars().all()
            return [
                MemoryItemDTO(
                    id=r.id, kind=r.kind, content=r.content,
                    metadata=r.meta or {}, score=0.0,
                )
                for r in rows
            ]
