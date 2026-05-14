"""
EventBus — async pub/sub used by every module.

Why this exists
---------------
Scawward is a swarm of loosely-coupled modules (vision, agent, executor,
UI, workflow). Direct imports between them creates a dependency hairball.
Instead, modules emit events; everyone interested subscribes.

Wire format
-----------
    Event("vision.screen.changed", payload={...}, source="vision")
    Event("agent.tool.called",     payload={...}, source="agent")
    Event("executor.action.done",  payload={...}, source="executor")

Topics use dotted namespaces so wildcards (`vision.*`) are easy.
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[["Event"], Awaitable[None]]


@dataclass(slots=True)
class Event:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = field(default_factory=time.time)


class EventBus:
    """In-process async pub/sub. Singleton-friendly."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._history: list[Event] = []
        self._history_max = 500
        self._lock = asyncio.Lock()

    # ─── Subscriptions ────────────────────────────────────────────
    def subscribe(self, topic_pattern: str, handler: Handler) -> Callable[[], None]:
        """Subscribe with optional glob pattern (e.g. ``vision.*``).

        Returns an `unsubscribe()` callable.
        """
        self._subs[topic_pattern].append(handler)
        logger.debug("subscribed handler to %s", topic_pattern)

        def _unsub() -> None:
            try:
                self._subs[topic_pattern].remove(handler)
            except ValueError:
                pass

        return _unsub

    # ─── Publishing ───────────────────────────────────────────────
    async def publish(self, event: Event) -> None:
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_max:
                self._history = self._history[-self._history_max :]

        matched: list[Handler] = []
        for pattern, handlers in self._subs.items():
            if fnmatch.fnmatchcase(event.topic, pattern):
                matched.extend(handlers)

        if not matched:
            return

        results = await asyncio.gather(
            *(self._safe_call(h, event) for h in matched), return_exceptions=True
        )
        for r in results:
            if isinstance(r, Exception):
                logger.exception("event handler failed: %s", r)

    async def emit(self, topic: str, payload: dict[str, Any] | None = None,
                   source: str = "unknown") -> Event:
        """Convenience wrapper around `publish`."""
        evt = Event(topic=topic, payload=payload or {}, source=source)
        await self.publish(evt)
        return evt

    # ─── Introspection ────────────────────────────────────────────
    def recent(self, n: int = 50) -> list[Event]:
        return list(self._history[-n:])

    # ─── Internals ────────────────────────────────────────────────
    @staticmethod
    async def _safe_call(handler: Handler, event: Event) -> None:
        try:
            await handler(event)
        except Exception:
            logger.exception("handler %s blew up on %s", handler, event.topic)


# Process-wide singleton (kept simple; swap for DI if you grow up).
_bus_singleton: EventBus | None = None


def get_bus() -> EventBus:
    global _bus_singleton
    if _bus_singleton is None:
        _bus_singleton = EventBus()
    return _bus_singleton
