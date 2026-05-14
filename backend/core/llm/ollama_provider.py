"""Ollama provider — local GPU inference, free and offline.

Speaks Ollama's `/api/chat` endpoint (OpenAI-style tool calling).
Converts the Anthropic-style internal format on the way in and out.

References:
  https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-chat-completion
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import httpx

from .base import LLMProvider, ProviderResponse, TextBlock, ToolUseBlock, UsageStats

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Pilot Scawward with a model running locally via Ollama."""

    name = "ollama"

    def __init__(
        self,
        host: str = "http://127.0.0.1:11434",
        default_model: str = "llama3.1:latest",
        request_timeout: float = 300.0,
    ) -> None:
        self.host = host.rstrip("/")
        self.default_model = default_model
        self.request_timeout = request_timeout

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
        ollama_model = model or self.default_model
        ollama_messages = self._convert_messages(system, messages)
        ollama_tools = self._convert_tools(tools)

        payload: dict[str, Any] = {
            "model": ollama_model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if ollama_tools:
            payload["tools"] = ollama_tools

        url = f"{self.host}/api/chat"
        logger.debug("ollama POST %s model=%s msgs=%d tools=%d",
                     url, ollama_model, len(ollama_messages), len(ollama_tools))

        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return self._convert_response(data)

    # ─── Conversion: messages ─────────────────────────────────────
    @staticmethod
    def _convert_messages(
        system_blocks: list[dict[str, Any]],
        anthropic_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Flatten Anthropic content blocks into Ollama's OpenAI-style messages."""
        out: list[dict[str, Any]] = []

        # 1. Concatenate every system block into one message.
        sys_text = "\n\n".join(
            (b.get("text") or "").strip()
            for b in system_blocks
            if isinstance(b, dict) and (b.get("text") or "").strip()
        )
        if sys_text:
            out.append({"role": "system", "content": sys_text})

        # 2. Walk the conversation.
        for msg in anthropic_messages:
            role = msg.get("role")
            content = msg.get("content")

            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue

            if not isinstance(content, list):
                out.append({"role": role, "content": str(content)})
                continue

            if role == "user":
                tool_results = [
                    b for b in content
                    if isinstance(b, dict) and b.get("type") == "tool_result"
                ]
                text_parts = [
                    (b.get("text") or "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                if tool_results:
                    for tr in tool_results:
                        tr_content = tr.get("content")
                        if isinstance(tr_content, str):
                            tool_text = tr_content
                        elif isinstance(tr_content, list):
                            tool_text = "\n".join(
                                (b.get("text") or "") if isinstance(b, dict) else str(b)
                                for b in tr_content
                            )
                        else:
                            tool_text = json.dumps(tr_content, ensure_ascii=False)
                        out.append({"role": "tool", "content": tool_text})
                elif text_parts:
                    out.append({"role": "user", "content": "\n".join(text_parts).strip()})

            elif role == "assistant":
                texts: list[str] = []
                tool_calls: list[dict[str, Any]] = []
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":
                        texts.append(b.get("text") or "")
                    elif b.get("type") == "tool_use":
                        tool_calls.append({
                            "function": {
                                "name": b.get("name", ""),
                                "arguments": b.get("input") or {},
                            },
                        })
                ass: dict[str, Any] = {
                    "role": "assistant",
                    "content": "\n".join(t for t in texts if t).strip(),
                }
                if tool_calls:
                    ass["tool_calls"] = tool_calls
                out.append(ass)

        return out

    # ─── Conversion: tools ────────────────────────────────────────
    @staticmethod
    def _convert_tools(anthropic_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Anthropic tool spec → Ollama (OpenAI-compatible) tool spec."""
        out: list[dict[str, Any]] = []
        for t in anthropic_tools:
            if not isinstance(t, dict) or "name" not in t:
                continue
            schema = t.get("input_schema") or {"type": "object", "properties": {}}
            out.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": schema,
                },
            })
        return out

    # ─── Conversion: response ─────────────────────────────────────
    @staticmethod
    def _convert_response(data: dict[str, Any]) -> ProviderResponse:
        msg = data.get("message") or {}
        blocks: list[Any] = []

        text = msg.get("content") or ""
        if text.strip():
            blocks.append(TextBlock(text=text))

        tool_calls = msg.get("tool_calls") or []
        for tc in tool_calls:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or {}
            # Ollama sometimes returns arguments as a JSON-encoded string;
            # sometimes as an object. Normalize to dict.
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"_raw": args}
            blocks.append(ToolUseBlock(
                id=tc.get("id") or _new_tool_id(),
                name=fn.get("name") or "",
                input=args if isinstance(args, dict) else {"_raw": args},
            ))

        stop_reason = "tool_use" if tool_calls else "end_turn"

        return ProviderResponse(
            content=blocks,
            stop_reason=stop_reason,
            usage=UsageStats(
                input_tokens=int(data.get("prompt_eval_count") or 0),
                output_tokens=int(data.get("eval_count") or 0),
            ),
        )


def _new_tool_id() -> str:
    """Mimic Anthropic's `toolu_xxx` id shape so logs look uniform."""
    return f"toolu_local_{int(time.time())}_{uuid.uuid4().hex[:8]}"


# Static check.
_check: type[LLMProvider] = OllamaProvider  # type: ignore[assignment]
