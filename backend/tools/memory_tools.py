"""Memory tools exposed to the agent.

Lets Claude explicitly stash long-lived knowledge about the user:
preferences, facts, recurring observations. Those are auto-injected
back into the system prompt on future turns via `MemoryEngine.recall`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .registry import ToolRegistry, ToolResult

if TYPE_CHECKING:
    from ..core.memory_engine import MemoryEngine


_ALLOWED_KINDS = {"fact", "preference", "observation"}


def register_memory_tools(reg: ToolRegistry, memory: "MemoryEngine") -> None:
    @reg.tool(
        name="remember",
        description=(
            "Persist a durable fact, user preference, or observation into "
            "long-term memory. Use this whenever the user reveals something "
            "you'd want to know in *future* sessions (e.g. 'I prefer French', "
            "'my main project lives at C:/.../OS', 'I'm building Scawward'). "
            "Do NOT use this for transient task state or for echoing the user."
        ),
        schema={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": sorted(_ALLOWED_KINDS),
                    "description": (
                        "'preference' = how the user likes things; "
                        "'fact' = stable truth about user/world; "
                        "'observation' = noticed pattern worth recalling."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Single self-contained sentence in the third person, "
                        "e.g. 'User prefers replies in French.'"
                    ),
                },
            },
            "required": ["kind", "content"],
        },
    )
    async def _remember(kind: str, content: str) -> ToolResult:
        kind = kind.strip().lower()
        if kind not in _ALLOWED_KINDS:
            return ToolResult.fail(
                f"unknown kind {kind!r}; expected one of {sorted(_ALLOWED_KINDS)}"
            )
        content = content.strip()
        if len(content) < 8:
            return ToolResult.fail("memory content is too short to be useful")

        doc_id = await memory.remember(kind, content, metadata={"source": "agent"})
        return ToolResult.success(
            f"stored {kind}: {content[:80]}",
            id=doc_id,
            kind=kind,
        )

    @reg.tool(
        name="recall",
        description=(
            "Search long-term memory for entries semantically related to a "
            "query. Useful when you suspect the user told you something "
            "earlier but it's not in the current conversation. Note: the most "
            "relevant memories are already injected into your system prompt; "
            "only call this when you need to dig deeper."
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
    )
    async def _recall(query: str, k: int = 5) -> ToolResult:
        items = await memory.recall(query, k=k)
        if not items:
            return ToolResult.success("no relevant memories found", items=[])
        rendered = [
            {"kind": m.kind, "content": m.content, "score": round(m.score, 3)}
            for m in items
        ]
        return ToolResult.success(
            f"recalled {len(rendered)} memor{'y' if len(rendered) == 1 else 'ies'}",
            items=rendered,
        )
