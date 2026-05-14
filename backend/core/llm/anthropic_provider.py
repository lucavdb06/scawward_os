"""Anthropic Claude provider.

Trivial wrapper because Anthropic's `Message` object already exposes
`.content` (with `.type`, `.text`, `.id`, `.name`, `.input` on each block),
`.stop_reason`, and `.usage.input_tokens` / `.usage.output_tokens`.

We *could* convert into our `ProviderResponse` dataclass for purity, but
that would just create a copy with the same shape. Returning the SDK object
is faster, keeps prompt-cache metadata intact, and the agent already uses
duck-typing on these attributes.
"""
from __future__ import annotations

import logging
from typing import Any, cast

from anthropic import AsyncAnthropic

from .base import LLMProvider, ProviderResponse

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """Plug Anthropic Claude into the agent loop."""

    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        self.client = AsyncAnthropic(api_key=api_key)

    async def create(
        self,
        *,
        model: str,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        resp = await self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            tools=tools,
            messages=messages,
        )
        return cast(ProviderResponse, resp)


# Static check (helps catch protocol drift early).
_check: type[LLMProvider] = AnthropicProvider  # type: ignore[assignment]
