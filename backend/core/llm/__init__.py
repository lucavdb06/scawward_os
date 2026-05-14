"""LLM providers — pluggable backends for the agentic loop.

Currently supported:
  - anthropic: paid, top-tier, function calling native, prompt caching
  - ollama:    local GPU, free, function calling for llama3.1 / qwen2.5

Both speak the same `LLMProvider` Protocol so `ScawwardAgent` doesn't care
which one is plugged in.
"""
from .base import (
    LLMProvider,
    ProviderResponse,
    TextBlock,
    ToolUseBlock,
    UsageStats,
)

__all__ = [
    "LLMProvider",
    "ProviderResponse",
    "TextBlock",
    "ToolUseBlock",
    "UsageStats",
]
