"""Tests for the OllamaProvider conversion + HTTP round-trip."""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from backend.core.llm.base import ProviderResponse, TextBlock, ToolUseBlock
from backend.core.llm.ollama_provider import OllamaProvider


# ─── Conversion: messages ─────────────────────────────────────────


def test_convert_messages_collapses_system_blocks() -> None:
    sys_blocks = [
        {"type": "text", "text": "You are SCAWWARD."},
        {"type": "text", "text": "Be concise."},
    ]
    out = OllamaProvider._convert_messages(sys_blocks, [])
    assert out[0]["role"] == "system"
    assert "SCAWWARD" in out[0]["content"]
    assert "concise" in out[0]["content"]


def test_convert_messages_plain_user_string() -> None:
    out = OllamaProvider._convert_messages([], [{"role": "user", "content": "hi"}])
    assert out == [{"role": "user", "content": "hi"}]


def test_convert_messages_assistant_with_tool_use() -> None:
    anthropic_msgs = [
        {"role": "user", "content": "list files"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Sure, listing now."},
            {"type": "tool_use", "id": "toolu_1", "name": "list_dir",
             "input": {"path": "/tmp"}},
        ]},
    ]
    out = OllamaProvider._convert_messages([], anthropic_msgs)
    assert out[0] == {"role": "user", "content": "list files"}
    ass = out[1]
    assert ass["role"] == "assistant"
    assert "listing" in ass["content"]
    assert ass["tool_calls"] == [{
        "function": {"name": "list_dir", "arguments": {"path": "/tmp"}}
    }]


def test_convert_messages_tool_result_becomes_tool_role() -> None:
    anthropic_msgs = [{
        "role": "user",
        "content": [{
            "type": "tool_result", "tool_use_id": "toolu_1",
            "content": json.dumps({"ok": True, "summary": "listed"}),
            "is_error": False,
        }],
    }]
    out = OllamaProvider._convert_messages([], anthropic_msgs)
    assert len(out) == 1
    assert out[0]["role"] == "tool"
    assert "listed" in out[0]["content"]


def test_convert_messages_handles_list_content_in_tool_result() -> None:
    """Anthropic may wrap tool_result content in a list of text blocks."""
    anthropic_msgs = [{
        "role": "user",
        "content": [{
            "type": "tool_result", "tool_use_id": "toolu_2",
            "content": [{"type": "text", "text": "part A"},
                        {"type": "text", "text": "part B"}],
        }],
    }]
    out = OllamaProvider._convert_messages([], anthropic_msgs)
    assert out[0]["role"] == "tool"
    assert "part A" in out[0]["content"]
    assert "part B" in out[0]["content"]


# ─── Conversion: tools ────────────────────────────────────────────


def test_convert_tools_wraps_in_openai_format() -> None:
    anthropic_tools = [{
        "name": "read_file",
        "description": "Read a file",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    }]
    out = OllamaProvider._convert_tools(anthropic_tools)
    assert out == [{
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }]


def test_convert_tools_handles_missing_schema() -> None:
    out = OllamaProvider._convert_tools([{"name": "nop", "description": "noop"}])
    assert out[0]["function"]["parameters"] == {"type": "object", "properties": {}}


# ─── Conversion: response ─────────────────────────────────────────


def test_convert_response_plain_text() -> None:
    data = {
        "message": {"role": "assistant", "content": "Hello there."},
        "prompt_eval_count": 12,
        "eval_count": 4,
    }
    r = OllamaProvider._convert_response(data)
    assert isinstance(r, ProviderResponse)
    assert len(r.content) == 1
    assert isinstance(r.content[0], TextBlock)
    assert r.content[0].text == "Hello there."
    assert r.stop_reason == "end_turn"
    assert r.usage.input_tokens == 12
    assert r.usage.output_tokens == 4


def test_convert_response_with_tool_call_dict_args() -> None:
    data = {
        "message": {
            "role": "assistant",
            "content": "Reading the file now.",
            "tool_calls": [{
                "function": {"name": "read_file", "arguments": {"path": "/x.txt"}}
            }],
        }
    }
    r = OllamaProvider._convert_response(data)
    # text block + tool use block
    assert len(r.content) == 2
    text_block, tool_block = r.content
    assert isinstance(text_block, TextBlock)
    assert isinstance(tool_block, ToolUseBlock)
    assert tool_block.name == "read_file"
    assert tool_block.input == {"path": "/x.txt"}
    assert tool_block.id.startswith("toolu_local_")
    assert r.stop_reason == "tool_use"


def test_convert_response_with_tool_call_string_args() -> None:
    """Some Ollama models return arguments as a JSON-encoded string."""
    data = {
        "message": {
            "role": "assistant", "content": "",
            "tool_calls": [{
                "function": {"name": "read_file",
                             "arguments": '{"path": "/y.txt"}'}
            }],
        }
    }
    r = OllamaProvider._convert_response(data)
    assert len(r.content) == 1  # no text, just tool
    assert isinstance(r.content[0], ToolUseBlock)
    assert r.content[0].input == {"path": "/y.txt"}


def test_convert_response_with_malformed_string_args() -> None:
    """If arguments string is not valid JSON, we don't crash — we capture it raw."""
    data = {
        "message": {
            "role": "assistant", "content": "",
            "tool_calls": [{
                "function": {"name": "x", "arguments": "not json"}
            }],
        }
    }
    r = OllamaProvider._convert_response(data)
    assert isinstance(r.content[0], ToolUseBlock)
    assert "_raw" in r.content[0].input


# ─── HTTP round-trip (mocked) ─────────────────────────────────────


class _FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, response_json: dict[str, Any]) -> None:
        self.captured: dict[str, Any] = {}
        self._response_json = response_json

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.captured["url"] = str(request.url)
        self.captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=self._response_json)


@pytest.mark.asyncio
async def test_create_round_trip(monkeypatch) -> None:
    fake = _FakeTransport({
        "message": {
            "role": "assistant",
            "content": "All good.",
        },
        "prompt_eval_count": 7,
        "eval_count": 3,
    })

    # Patch httpx.AsyncClient so the provider uses our fake transport.
    real_async_client = httpx.AsyncClient

    def _patched(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = fake
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _patched)

    provider = OllamaProvider(host="http://x:11434", default_model="llama3.1:latest")
    response = await provider.create(
        model="llama3.1:latest",
        system=[{"type": "text", "text": "You are SCAWWARD."}],
        messages=[{"role": "user", "content": "ping"}],
        tools=[{"name": "ping_tool", "description": "p",
                "input_schema": {"type": "object", "properties": {}}}],
        max_tokens=64,
        temperature=0.1,
    )

    # Outgoing request shape
    body = fake.captured["body"]
    assert body["model"] == "llama3.1:latest"
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0.1, "num_predict": 64}
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1] == {"role": "user", "content": "ping"}
    assert body["tools"][0]["function"]["name"] == "ping_tool"

    # Response shape
    assert response.stop_reason == "end_turn"
    assert response.content[0].text == "All good."
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 3
