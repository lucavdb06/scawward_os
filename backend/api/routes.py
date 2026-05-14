"""REST routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import __version__
from ..config import get_settings
from ..modules.workflow_engine import Step, Workflow
from .deps import AppStack, get_stack
from .schemas import (
    CommandRequest,
    CommandResponse,
    HealthResponse,
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
    return HealthResponse(
        version=__version__,
        tools=stack.tools.names(),
        has_api_key=bool(cfg.anthropic_api_key),
    )


@router.post("/command", response_model=CommandResponse)
async def run_command(req: CommandRequest,
                      stack: AppStack = Depends(get_stack)) -> CommandResponse:
    if not get_settings().anthropic_api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured")
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
