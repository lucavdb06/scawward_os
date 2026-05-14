"""LLM provider interface — quacks like Anthropic's Message.

We keep the *internal* conversation format Anthropic-style (content blocks
with `tool_use` / `tool_result`) because it's the most expressive option.
Each provider implementation handles its own translation when calling the
remote API and shapes the response back into this neutral format.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass
class TextBlock:
    text: str = ""
    type: Literal["text"] = "text"


@dataclass
class ToolUseBlock:
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    type: Literal["tool_use"] = "tool_use"


ContentBlock = TextBlock | ToolUseBlock


@dataclass
class UsageStats:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ProviderResponse:
    """Mimics `anthropic.types.Message` so the agent loop is provider-agnostic.

    The agent only accesses: `.content` (iterable of blocks each with `.type`),
    `.stop_reason`, and `.usage.input_tokens` / `.usage.output_tokens`.
    """
    content: list[ContentBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"        # "end_turn" | "tool_use" | "max_tokens"
    usage: UsageStats = field(default_factory=UsageStats)


@runtime_checkable
class LLMProvider(Protocol):
    """Every provider must support a single coroutine: `create(...)`."""
    name: str

    async def create(
        self,
        *,
        model: str,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse: ...
