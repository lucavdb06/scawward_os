"""
CommandProcessor — natural language → executed action.

This is the highest-level entry point for the API/UI:
just a thin wrapper that hands off to ScawwardAgent and emits the right events.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from ..core.event_bus import EventBus, get_bus
from ..core.scawward_agent import ScawwardAgent

logger = logging.getLogger(__name__)


class CommandProcessor:
    def __init__(self, agent: ScawwardAgent, bus: EventBus | None = None) -> None:
        self.agent = agent
        self.bus = bus or get_bus()

    async def run(self, text: str) -> dict[str, Any]:
        await self.bus.emit("command.received", {"text": text}, source="command_processor")
        turn = await self.agent.chat(text)
        await self.bus.emit("command.completed", {
            "text": text, "tool_calls": len(turn.tool_calls), "usage": turn.usage,
        }, source="command_processor")
        return {
            "answer": turn.final_text,
            "tool_calls": turn.tool_calls,
            "usage": turn.usage,
            "iterations": turn.iterations,
        }

    async def stream(self, text: str) -> AsyncIterator[dict[str, Any]]:
        await self.bus.emit("command.received", {"text": text}, source="command_processor")
        async for ev in self.agent.stream(text):
            yield ev
        await self.bus.emit("command.completed", {"text": text}, source="command_processor")
