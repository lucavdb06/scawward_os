"""
ContextManager — a rolling snapshot of "what the user is doing right now".

Sources of context:
  - Active OS window title (foreground app)
  - Recent screenshots (delegated to vision module)
  - Recent user commands & agent actions
  - Open files / current working dir
  - Time of day / calendar (later)

The ContextManager is *cheap to read* and *expensive only when it has to
re-snapshot*. It exposes a `serialize_for_llm()` that returns a compact
text block to inject into the agent's system prompt.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .event_bus import Event, EventBus, get_bus

logger = logging.getLogger(__name__)


@dataclass
class ContextSnapshot:
    timestamp: float
    active_window: str | None = None
    foreground_app: str | None = None
    cwd: str | None = None
    screen_summary: str | None = None
    recent_actions: list[str] = field(default_factory=list)
    recent_messages: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        """Compact, token-efficient context for the LLM."""
        lines = ["<current_context>"]
        if self.foreground_app:
            lines.append(f"  active_app: {self.foreground_app}")
        if self.active_window:
            lines.append(f"  window_title: {self.active_window}")
        if self.cwd:
            lines.append(f"  cwd: {self.cwd}")
        if self.screen_summary:
            lines.append(f"  screen: {self.screen_summary}")
        if self.recent_actions:
            lines.append("  recent_actions:")
            for a in self.recent_actions[-5:]:
                lines.append(f"    - {a}")
        if self.recent_messages:
            lines.append("  recent_user_messages:")
            for m in self.recent_messages[-3:]:
                lines.append(f"    - {m}")
        lines.append("</current_context>")
        return "\n".join(lines)


class ContextManager:
    """Aggregates real-time signals into a single context object."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self.bus = bus or get_bus()
        self._snapshot = ContextSnapshot(timestamp=time.time())
        self._actions: deque[str] = deque(maxlen=20)
        self._messages: deque[str] = deque(maxlen=10)
        self._wire_events()

    # ─── Public API ───────────────────────────────────────────────
    def snapshot(self) -> ContextSnapshot:
        snap = ContextSnapshot(
            timestamp=time.time(),
            active_window=self._snapshot.active_window,
            foreground_app=self._snapshot.foreground_app,
            cwd=self._snapshot.cwd,
            screen_summary=self._snapshot.screen_summary,
            recent_actions=list(self._actions),
            recent_messages=list(self._messages),
            extras=dict(self._snapshot.extras),
        )
        return snap

    def update_screen(self, summary: str) -> None:
        self._snapshot.screen_summary = summary

    def update_window(self, title: str | None, app: str | None) -> None:
        self._snapshot.active_window = title
        self._snapshot.foreground_app = app

    def update_cwd(self, cwd: str) -> None:
        self._snapshot.cwd = cwd

    def serialize_for_llm(self) -> str:
        return self.snapshot().to_prompt_block()

    # ─── Event wiring ─────────────────────────────────────────────
    def _wire_events(self) -> None:
        self.bus.subscribe("vision.screen.summary", self._on_screen)
        self.bus.subscribe("vision.window.changed", self._on_window)
        self.bus.subscribe("user.message", self._on_message)
        self.bus.subscribe("executor.action.done", self._on_action)

    async def _on_screen(self, evt: Event) -> None:
        s = evt.payload.get("summary")
        if s:
            self.update_screen(str(s))

    async def _on_window(self, evt: Event) -> None:
        self.update_window(evt.payload.get("title"), evt.payload.get("app"))

    async def _on_message(self, evt: Event) -> None:
        text = evt.payload.get("text")
        if text:
            self._messages.append(str(text))

    async def _on_action(self, evt: Event) -> None:
        name = evt.payload.get("tool", "?")
        ok = "ok" if evt.payload.get("ok", True) else "fail"
        self._actions.append(f"{name}[{ok}]")
