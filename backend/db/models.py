"""
SQLAlchemy 2.x ORM models.

Schema overview
---------------
conversations          : top-level chat threads
messages               : turns inside a conversation
tool_executions        : every tool call (success or fail) for audit
memory_items           : episodic + semantic memories
user_patterns          : aggregated behavioral patterns ("user does X at Y")
workflows              : saved workflow definitions
workflow_runs          : execution history of workflows
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))                  # user|assistant|tool
    content: Mapped[str] = mapped_column(Text)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    message_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(60), index=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSON)
    output: Mapped[dict[str, Any]] = mapped_column(JSON)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    embedded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (Index("ix_memory_kind_created", "kind", "created_at"),)


class UserPattern(Base):
    """Aggregated heuristic patterns: 'user opens X every morning at 9'."""
    __tablename__ = "user_patterns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(default=0.0)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorkflowDef(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    description: Mapped[str | None] = mapped_column(Text)
    spec: Mapped[dict[str, Any]] = mapped_column(JSON)             # serialized Workflow
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workflow_id: Mapped[str] = mapped_column(String(60), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    ok: Mapped[bool | None] = mapped_column(Boolean)
    outcomes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
