"""Async DB engine + session factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import get_settings
from .models import Base

_engine = None
_Session: async_sessionmaker[AsyncSession] | None = None


def _init() -> None:
    global _engine, _Session
    if _engine is not None:
        return
    cfg = get_settings()
    _engine = create_async_engine(cfg.db_url, future=True, echo=cfg.debug)
    _Session = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    _init()
    assert _engine is not None
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    _init()
    assert _Session is not None
    async with _Session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
