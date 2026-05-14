"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ─── Commands ────────────────────────────────────────────────────────
class CommandRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000)
    conversation_id: str | None = None
    stream: bool = False


class ToolCallTrace(BaseModel):
    name: str
    input: dict[str, Any]
    result: dict[str, Any]


class CommandResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallTrace] = []
    usage: dict[str, int] = Field(default_factory=dict)
    iterations: int = 0


# ─── Memory ──────────────────────────────────────────────────────────
class MemoryQuery(BaseModel):
    query: str
    k: int = 5
    kinds: list[str] | None = None


class MemoryHit(BaseModel):
    id: str
    kind: str
    content: str
    metadata: dict[str, Any]
    score: float


# ─── Workflows ───────────────────────────────────────────────────────
class StepSpec(BaseModel):
    id: str
    kind: Literal["prompt", "tool", "python"]
    prompt: str | None = None
    tool: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    optional: bool = False


class WorkflowSpec(BaseModel):
    id: str
    description: str = ""
    steps: list[StepSpec]


class StepOutcomeOut(BaseModel):
    step_id: str
    ok: bool
    output: Any
    error: str | None = None


# ─── System ──────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    ok: bool = True
    version: str
    tools: list[str] = []
    has_api_key: bool = False
    llm_provider: str = "anthropic"
    llm_model: str = ""
    llm_ready: bool = False
    ollama_reachable: bool = False
    ollama_models: list[str] = []


class LLMPreference(BaseModel):
    provider: Literal["anthropic", "ollama"]
    ollama_model: str | None = None


class ChatHistoryResponse(BaseModel):
    events: list[dict[str, Any]]


# ─── WebSocket events ────────────────────────────────────────────────
class WSEvent(BaseModel):
    type: Literal["text", "tool", "usage", "done", "error", "system"]
    data: dict[str, Any] = Field(default_factory=dict)
