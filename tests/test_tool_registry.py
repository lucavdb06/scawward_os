import pytest

from backend.tools.registry import ToolRegistry, ToolResult


@pytest.mark.asyncio
async def test_register_and_execute_async_tool() -> None:
    reg = ToolRegistry()

    @reg.tool(
        name="add",
        description="add two ints",
        schema={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    )
    async def add(a: int, b: int) -> ToolResult:
        return ToolResult.success(f"{a+b}", value=a + b)

    out = await reg.execute("add", {"a": 2, "b": 3})
    assert out.ok
    assert out.data["value"] == 5


@pytest.mark.asyncio
async def test_missing_required_field_rejected() -> None:
    reg = ToolRegistry()

    @reg.tool(name="x", description="x", schema={
        "type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"],
    })
    async def fn(a: int) -> ToolResult:
        return ToolResult.success("ok")

    out = await reg.execute("x", {})
    assert not out.ok
    assert "missing required" in out.summary
