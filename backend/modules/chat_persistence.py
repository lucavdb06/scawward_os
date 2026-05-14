"""Turn streaming events into Message rows for the UI conversation."""
from __future__ import annotations

import json
import logging
from typing import Any

from ..db.conversation_repo import append_message, get_or_create_ui_conversation_id

logger = logging.getLogger(__name__)


async def persist_stream_turn(user_text: str, events: list[dict[str, Any]]) -> None:
    """Persist one turn in *chronological* order so reload replays correctly."""
    if not user_text.strip():
        return
    try:
        cid = await get_or_create_ui_conversation_id()
    except Exception:
        logger.exception("could not open ui conversation")
        return

    try:
        await append_message(cid, "user", user_text.strip())
    except Exception:
        logger.exception("persist user message failed")
        return

    buf: list[str] = []
    async def flush_text() -> None:
        nonlocal buf
        merged = "".join(buf).strip()
        if merged:
            try:
                await append_message(cid, "assistant", merged)
            except Exception:
                logger.exception("persist assistant chunk failed")
        buf.clear()

    for ev in events:
        et = ev.get("type")
        if et == "text":
            chunk = (ev.get("data") or {}).get("text") or ""
            if chunk.startswith("\n> "):
                continue
            buf.append(chunk)
        elif et == "tool":
            await flush_text()
            data = ev.get("data") or {}
            try:
                blob = json.dumps(
                    {
                        "name": data.get("name"),
                        "input": data.get("input"),
                        "result": data.get("result"),
                    },
                    ensure_ascii=False,
                    default=str,
                )
                await append_message(cid, "tool", blob)
            except Exception:
                logger.exception("persist tool message failed")

    await flush_text()
