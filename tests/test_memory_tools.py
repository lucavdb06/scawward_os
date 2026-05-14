"""Tests for the `remember` / `recall` agent tools and the recall-block formatter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from backend.core.memory_engine import MemoryEngine, MemoryItem
from backend.core.scawward_agent import ScawwardAgent
from backend.tools.memory_tools import register_memory_tools
from backend.tools.registry import ToolRegistry


# ─── Fakes ───────────────────────────────────────────────────────────


@dataclass
class _FakeVector:
    """In-memory stand-in for ChromaVectorStore."""
    stored: list[MemoryItem] = field(default_factory=list)
    query_return: list[MemoryItem] = field(default_factory=list)

    async def upsert(self, doc_id: str, text: str, metadata: dict[str, Any]) -> None:
        self.stored.append(
            MemoryItem(id=doc_id, kind=metadata.get("kind", "fact"),
                       content=text, metadata=metadata)
        )

    async def query(self, text: str, k: int = 5,
                    where: dict[str, Any] | None = None) -> list[MemoryItem]:
        return list(self.query_return[:k])


@dataclass
class _FakeEpisodic:
    """In-memory stand-in for SqlEpisodicStore."""
    logs: list[MemoryItem] = field(default_factory=list)
    _counter: int = 0

    async def log(self, kind: str, content: str, metadata: dict[str, Any]) -> str:
        self._counter += 1
        doc_id = f"ep-{self._counter}"
        self.logs.append(MemoryItem(id=doc_id, kind=kind,
                                    content=content, metadata=metadata))
        return doc_id

    async def recent(self, n: int = 20) -> list[MemoryItem]:
        return list(self.logs[-n:])


# ─── Tool: `remember` ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remember_tool_persists_preference() -> None:
    vector, episodic = _FakeVector(), _FakeEpisodic()
    memory = MemoryEngine(vector, episodic)
    reg = ToolRegistry()
    register_memory_tools(reg, memory)

    out = await reg.execute(
        "remember",
        {"kind": "preference", "content": "User prefers replies in French."},
    )

    assert out.ok, out.summary
    assert out.data["kind"] == "preference"
    # Hit both stores: episodic log + semantic embedding.
    assert len(episodic.logs) == 1
    assert len(vector.stored) == 1
    assert "French" in vector.stored[0].content


@pytest.mark.asyncio
async def test_remember_rejects_unknown_kind() -> None:
    memory = MemoryEngine(_FakeVector(), _FakeEpisodic())
    reg = ToolRegistry()
    register_memory_tools(reg, memory)

    out = await reg.execute("remember", {"kind": "secret", "content": "x" * 20})
    assert not out.ok
    assert "unknown kind" in out.summary


@pytest.mark.asyncio
async def test_remember_rejects_short_content() -> None:
    memory = MemoryEngine(_FakeVector(), _FakeEpisodic())
    reg = ToolRegistry()
    register_memory_tools(reg, memory)

    out = await reg.execute("remember", {"kind": "fact", "content": "hi"})
    assert not out.ok
    assert "too short" in out.summary


# ─── Tool: `recall` ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recall_tool_returns_items() -> None:
    vector = _FakeVector(query_return=[
        MemoryItem(id="m1", kind="preference", content="User prefers French.",
                   metadata={}, score=0.87),
    ])
    memory = MemoryEngine(vector, _FakeEpisodic())
    reg = ToolRegistry()
    register_memory_tools(reg, memory)

    out = await reg.execute("recall", {"query": "language"})

    assert out.ok
    assert out.data["items"] == [
        {"kind": "preference", "content": "User prefers French.", "score": 0.87}
    ]


# ─── Formatter: `_format_recalled` ───────────────────────────────────


def test_format_recalled_empty_returns_empty_string() -> None:
    assert ScawwardAgent._format_recalled([]) == ""


def test_format_recalled_orders_preferences_first() -> None:
    items = [
        MemoryItem(id="a", kind="action",
                   content="read_file(path=foo.txt)", metadata={}),
        MemoryItem(id="p", kind="preference",
                   content="User prefers French.", metadata={}),
        MemoryItem(id="f", kind="fact",
                   content="User is building Scawward.", metadata={}),
    ]
    rendered = ScawwardAgent._format_recalled(items)

    assert rendered.startswith("<long_term_memory>")
    assert rendered.endswith("</long_term_memory>")
    # preference appears before fact appears before action
    pref_idx = rendered.find("[preference]")
    fact_idx = rendered.find("[fact]")
    action_idx = rendered.find("[action]")
    assert 0 < pref_idx < fact_idx < action_idx


def test_format_recalled_caps_long_content() -> None:
    long = "x" * 500
    items = [MemoryItem(id="x", kind="fact", content=long, metadata={})]
    rendered = ScawwardAgent._format_recalled(items)
    assert "..." in rendered
    # The body line itself should never exceed ~210 chars (prefix + content).
    body_line = next(ln for ln in rendered.splitlines() if ln.startswith("  - [fact]"))
    assert len(body_line) <= 215
