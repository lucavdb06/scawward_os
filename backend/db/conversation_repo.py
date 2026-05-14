"""Persistence for UI chat turns (Conversation + Message rows)."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, select

from .models import Conversation, Message
from .session import get_session

UI_CHAT_TITLE = "__ui_main__"


async def get_or_create_ui_conversation_id() -> str:
    async with get_session() as s:
        r = await s.execute(
            select(Conversation).where(Conversation.title == UI_CHAT_TITLE).limit(1)
        )
        row = r.scalar_one_or_none()
        if row:
            return row.id
        c = Conversation(title=UI_CHAT_TITLE)
        s.add(c)
        await s.flush()
        return c.id


async def append_message(conversation_id: str, role: str, content: str) -> str:
    async with get_session() as s:
        m = Message(conversation_id=conversation_id, role=role, content=content)
        s.add(m)
        await s.flush()
        return m.id


async def list_ui_messages(limit: int = 500) -> list[dict[str, Any]]:
    """Return messages oldest-first for replay."""
    cid = await get_or_create_ui_conversation_id()
    async with get_session() as s:
        r = await s.execute(
            select(Message)
            .where(Message.conversation_id == cid)
            .order_by(Message.created_at)
            .limit(limit)
        )
        rows = r.scalars().all()
        return [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
            for m in rows
        ]


def messages_to_chat_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map DB rows → WebSocket-shaped events for the React UI."""
    out: list[dict[str, Any]] = []
    for m in rows:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "user":
            out.append({"type": "text", "data": {"text": f"\n> {content}\n"}})
        elif role == "assistant":
            if content:
                out.append({"type": "text", "data": {"text": content}})
        elif role == "tool":
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                payload = {"name": "unknown", "input": {}, "result": None}
            out.append({
                "type": "tool",
                "data": {
                    "name": payload.get("name", "tool"),
                    "input": payload.get("input"),
                    "result": payload.get("result"),
                },
            })
    return out
