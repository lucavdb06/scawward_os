import pytest

from backend.core.event_bus import EventBus


@pytest.mark.asyncio
async def test_subscribe_and_emit_simple() -> None:
    bus = EventBus()
    received: list[str] = []

    async def handler(evt) -> None:
        received.append(evt.payload["msg"])

    bus.subscribe("user.message", handler)
    await bus.emit("user.message", {"msg": "hi"})
    assert received == ["hi"]


@pytest.mark.asyncio
async def test_glob_pattern_matching() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def h(evt) -> None:
        seen.append(evt.topic)

    bus.subscribe("vision.*", h)
    await bus.emit("vision.screen.summary", {})
    await bus.emit("vision.window.changed", {})
    await bus.emit("agent.tool.requested", {})
    assert seen == ["vision.screen.summary", "vision.window.changed"]


@pytest.mark.asyncio
async def test_unsubscribe() -> None:
    bus = EventBus()
    seen: list[str] = []

    async def h(evt) -> None:
        seen.append(evt.topic)

    unsub = bus.subscribe("x", h)
    await bus.emit("x")
    unsub()
    await bus.emit("x")
    assert len(seen) == 1
