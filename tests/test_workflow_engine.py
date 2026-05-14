import pytest

from backend.modules.workflow_engine import Step, Workflow, WorkflowEngine
from backend.tools.registry import ToolRegistry, ToolResult


class _DummyAgent:
    async def chat(self, text: str):
        from backend.core.scawward_agent import AgentTurn
        return AgentTurn(user_input=text, final_text=f"echo:{text}",
                         tool_calls=[], usage={"input": 0, "output": 0}, iterations=1)


@pytest.mark.asyncio
async def test_workflow_runs_in_order_and_interpolates() -> None:
    reg = ToolRegistry()

    @reg.tool(name="upper", description="uppercase",
              schema={"type": "object", "properties": {"s": {"type": "string"}},
                      "required": ["s"]})
    async def up(s: str) -> ToolResult:
        return ToolResult.success(s.upper(), text=s.upper())

    eng = WorkflowEngine(_DummyAgent(), reg)        # type: ignore[arg-type]
    wf = Workflow(id="t", steps=[
        Step(id="a", kind="prompt", prompt="hello"),
        Step(id="b", kind="tool", tool="upper", input={"s": "${a}"}),
    ])
    outcomes = await eng.run(wf)
    assert all(o.ok for o in outcomes)
    assert outcomes[1].output["text"] == "ECHO:HELLO"
