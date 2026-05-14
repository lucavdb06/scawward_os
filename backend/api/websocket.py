"""WebSocket endpoint — bidirectional streaming chat + live event feed."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.event_bus import Event
from .deps import get_stack

logger = logging.getLogger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    """Client sends `{"text": "..."}`, server streams JSON events back."""
    await websocket.accept()
    stack = get_stack()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                text = (msg.get("text") or "").strip()
            except Exception:
                await _send(websocket, "error", {"message": "bad json"})
                continue
            if not text:
                continue
            try:
                async for ev in stack.commands.stream(text):
                    await _send(websocket, ev["type"], ev)
            except Exception as e:
                logger.exception("stream failed")
                await _send(websocket, "error", {"message": repr(e)})
    except WebSocketDisconnect:
        return


@ws_router.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    """Subscribe to *all* internal events. Useful for the live debug HUD."""
    await websocket.accept()
    stack = get_stack()
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=1000)

    async def forward(evt: Event) -> None:
        try:
            queue.put_nowait(evt)
        except asyncio.QueueFull:
            pass

    unsub = stack.bus.subscribe("*", forward)
    try:
        while True:
            evt = await queue.get()
            await _send(websocket, "event", {
                "topic": evt.topic, "source": evt.source,
                "ts": evt.ts, "payload": evt.payload,
            })
    except WebSocketDisconnect:
        return
    finally:
        unsub()


async def _send(ws: WebSocket, type_: str, data: dict[str, Any]) -> None:
    try:
        await ws.send_text(json.dumps({"type": type_, "data": data}, default=str))
    except Exception:
        pass
