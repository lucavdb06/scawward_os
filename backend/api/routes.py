"""REST routes."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException

from .. import __version__
from ..config import get_settings
from ..db.conversation_repo import list_ui_messages, messages_to_chat_events
from ..modules.workflow_engine import Step, Workflow
from .deps import AppStack, get_stack
from .schemas import (
    ChatHistoryResponse,
    CommandRequest,
    CommandResponse,
    HealthResponse,
    LLMPreference,
    MemoryHit,
    MemoryQuery,
    StepOutcomeOut,
    ToolCallTrace,
    WorkflowSpec,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(stack: AppStack = Depends(get_stack)) -> HealthResponse:
    cfg = get_settings()
    ollama_ok = False
    ollama_models: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{cfg.ollama_host.rstrip('/')}/api/tags")
            if r.status_code == 200:
                ollama_ok = True
                ollama_models = [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]
    except Exception:
        pass

    has_key = bool((cfg.anthropic_api_key or "").strip())
    ready = (
        stack.llm_provider_name == "ollama" and ollama_ok
    ) or (
        stack.llm_provider_name == "anthropic" and has_key
    )
    return HealthResponse(
        version=__version__,
        tools=stack.tools.names(),
        has_api_key=has_key,
        llm_provider=stack.llm_provider_name,
        llm_model=stack.active_llm_label(),
        llm_ready=ready,
        ollama_reachable=ollama_ok,
        ollama_models=sorted(ollama_models),
    )


@router.post("/llm", response_model=dict)
async def set_llm_pref(body: LLMPreference, stack: AppStack = Depends(get_stack)) -> dict:
    try:
        stack.set_llm(body.provider, body.ollama_model)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "ok": True,
        "provider": stack.llm_provider_name,
        "model": stack.active_llm_label(),
    }


@router.get("/chat/history", response_model=ChatHistoryResponse)
async def chat_history() -> ChatHistoryResponse:
    rows = await list_ui_messages()
    return ChatHistoryResponse(events=messages_to_chat_events(rows))


@router.post("/command", response_model=CommandResponse)
async def run_command(req: CommandRequest,
                      stack: AppStack = Depends(get_stack)) -> CommandResponse:
    cfg = get_settings()
    has_key = bool((cfg.anthropic_api_key or "").strip())
    if stack.llm_provider_name == "anthropic" and not has_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured")
    if stack.llm_provider_name == "ollama":
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{cfg.ollama_host.rstrip('/')}/api/tags")
                if r.status_code != 200:
                    raise HTTPException(503, "Ollama not reachable")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(503, f"Ollama not reachable: {e!r}") from e
    out = await stack.commands.run(req.text)
    return CommandResponse(
        answer=out["answer"],
        tool_calls=[ToolCallTrace(**tc) for tc in out["tool_calls"]],
        usage=out["usage"],
        iterations=out["iterations"],
    )


@router.post("/memory/recall", response_model=list[MemoryHit])
async def memory_recall(q: MemoryQuery,
                        stack: AppStack = Depends(get_stack)) -> list[MemoryHit]:
    hits = await stack.memory.recall(q.query, k=q.k, kinds=q.kinds)
    return [MemoryHit(id=h.id, kind=h.kind, content=h.content,
                      metadata=h.metadata, score=h.score) for h in hits]


@router.post("/workflows/run", response_model=list[StepOutcomeOut])
async def run_workflow(spec: WorkflowSpec,
                       stack: AppStack = Depends(get_stack)) -> list[StepOutcomeOut]:
    wf = Workflow(
        id=spec.id,
        description=spec.description,
        steps=[Step(**s.model_dump(exclude_none=True)) for s in spec.steps],
    )
    outcomes = await stack.workflows.run(wf)
    return [StepOutcomeOut(step_id=o.step_id, ok=o.ok, output=o.output, error=o.error)
            for o in outcomes]


@router.get("/tools")
async def list_tools(stack: AppStack = Depends(get_stack)) -> dict[str, list[dict]]:
    return {"tools": stack.tools.schema_for_anthropic()}


@router.get("/events/recent")
async def recent_events(n: int = 50, stack: AppStack = Depends(get_stack)) -> list[dict]:
    return [
        {"id": e.id, "topic": e.topic, "source": e.source, "ts": e.ts, "payload": e.payload}
        for e in stack.bus.recent(n)
    ]
