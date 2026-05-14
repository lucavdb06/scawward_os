"""
WorkflowEngine — declarative multi-step plans the agent can execute.
(Scawward subsystem.)

A workflow is a list of Steps. Each Step is either:
  * `prompt`  → re-invoke the agent with a fresh sub-instruction;
  * `tool`    → call a registered tool directly;
  * `python`  → invoke a Python callable for custom logic.

Steps share a `WorkflowContext` so later steps can reference earlier outputs
via `${step_id}`.

Example
-------
    wf = Workflow(
        id="morning_brief",
        steps=[
            Step(id="news",  kind="prompt",
                 prompt="Search top 3 AI news from today, summarize."),
            Step(id="cal",   kind="tool", tool="shell",
                 input={"command": "echo TODO read calendar"}),
            Step(id="brief", kind="prompt",
                 prompt="Combine ${news} and ${cal} into a 6-line morning brief."),
        ],
    )
    await engine.run(wf)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..core.event_bus import EventBus, get_bus
from ..core.scawward_agent import ScawwardAgent
from ..tools.registry import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\$\{(\w+)\}")


@dataclass
class Step:
    id: str
    kind: str                              # "prompt" | "tool" | "python"
    prompt: str | None = None
    tool: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    fn: Callable[[dict[str, Any]], Awaitable[Any]] | None = None
    optional: bool = False                 # if True, errors don't abort run


@dataclass
class Workflow:
    id: str
    steps: list[Step]
    description: str = ""


@dataclass
class StepOutcome:
    step_id: str
    ok: bool
    output: Any
    error: str | None = None


class WorkflowEngine:
    def __init__(self, agent: ScawwardAgent, tools: ToolRegistry,
                 bus: EventBus | None = None) -> None:
        self.agent = agent
        self.tools = tools
        self.bus = bus or get_bus()

    async def run(self, wf: Workflow) -> list[StepOutcome]:
        ctx: dict[str, Any] = {}
        outcomes: list[StepOutcome] = []
        await self.bus.emit("workflow.started", {"id": wf.id}, source="workflow")

        for step in wf.steps:
            await self.bus.emit("workflow.step.started",
                                {"workflow": wf.id, "step": step.id}, source="workflow")
            try:
                output = await self._run_step(step, ctx)
                ctx[step.id] = output
                outcomes.append(StepOutcome(step.id, True, output))
            except Exception as e:
                logger.exception("workflow %s step %s failed", wf.id, step.id)
                outcomes.append(StepOutcome(step.id, False, None, error=repr(e)))
                if not step.optional:
                    await self.bus.emit("workflow.aborted",
                                        {"id": wf.id, "step": step.id}, source="workflow")
                    return outcomes

        await self.bus.emit("workflow.completed", {"id": wf.id}, source="workflow")
        return outcomes

    # ─── Step dispatch ────────────────────────────────────────────
    async def _run_step(self, step: Step, ctx: dict[str, Any]) -> Any:
        if step.kind == "prompt":
            assert step.prompt
            prompt = self._interpolate(step.prompt, ctx)
            turn = await self.agent.chat(prompt)
            return turn.final_text

        if step.kind == "tool":
            assert step.tool
            input_ = {k: self._interpolate(v, ctx) if isinstance(v, str) else v
                      for k, v in step.input.items()}
            result: ToolResult = await self.tools.execute(step.tool, input_)
            if not result.ok:
                raise RuntimeError(result.summary)
            return result.data

        if step.kind == "python":
            assert step.fn
            return await step.fn(ctx)

        raise ValueError(f"unknown step kind: {step.kind}")

    @staticmethod
    def _interpolate(text: str, ctx: dict[str, Any]) -> str:
        def sub(m: re.Match[str]) -> str:
            key = m.group(1)
            value = ctx.get(key, m.group(0))
            return str(value)
        return _PLACEHOLDER.sub(sub, text)
