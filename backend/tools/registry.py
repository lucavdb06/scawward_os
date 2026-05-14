"""
ToolRegistry — converts Python callables into Anthropic-compatible tool defs.

Usage
-----
    registry = ToolRegistry()

    @registry.tool(
        name="read_file",
        description="Read a UTF-8 text file from disk.",
        schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
    async def read_file(path: str) -> ToolResult:
        ...

    schema = registry.schema_for_anthropic()  # → list[dict]
    result = await registry.execute("read_file", {"path": "..."})
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    ok: bool
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "summary": self.summary, "data": self.data}

    @classmethod
    def success(cls, summary: str, **data: Any) -> "ToolResult":
        return cls(ok=True, summary=summary, data=data)

    @classmethod
    def fail(cls, summary: str, **data: Any) -> "ToolResult":
        return cls(ok=False, summary=summary, data=data)


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any]
    fn: Callable[..., Awaitable[ToolResult] | ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # ─── Registration ─────────────────────────────────────────────
    def tool(self, *, name: str, description: str,
             schema: dict[str, Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register(ToolSpec(name=name, description=description,
                                   schema=schema, fn=fn))
            return fn
        return decorator

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            logger.warning("tool %s re-registered, overwriting", spec.name)
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    # ─── Anthropic schema ─────────────────────────────────────────
    def schema_for_anthropic(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "input_schema": s.schema,
            }
            for s in self._tools.values()
        ]

    # ─── Execution ────────────────────────────────────────────────
    async def execute(self, name: str, input_: dict[str, Any]) -> ToolResult:
        spec = self._tools.get(name)
        if not spec:
            return ToolResult.fail(f"unknown tool: {name}")

        try:
            self._validate(spec.schema, input_)
        except ValueError as e:
            return ToolResult.fail(f"invalid input: {e}")

        try:
            result = spec.fn(**input_)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, ToolResult):
                result = ToolResult.success("ok", result=result)
            return result
        except Exception as e:
            logger.exception("tool %s raised", name)
            return ToolResult.fail(f"exception: {e!r}")

    # ─── Tiny JSON-schema validator (just required + types) ───────
    @staticmethod
    def _validate(schema: dict[str, Any], data: dict[str, Any]) -> None:
        for key in schema.get("required", []):
            if key not in data:
                raise ValueError(f"missing required field '{key}'")
        types_map = {
            "string": str, "integer": int, "number": (int, float),
            "boolean": bool, "array": list, "object": dict,
        }
        for k, prop in schema.get("properties", {}).items():
            if k not in data:
                continue
            t = prop.get("type")
            if t and t in types_map and not isinstance(data[k], types_map[t]):
                raise ValueError(f"field '{k}' must be {t}")


# ─── Factory: wires every concrete tool to a SystemExecutor ──────────
def build_default_registry(
    executor: "Any",
    memory: "Any | None" = None,
) -> ToolRegistry:
    """Register all built-in tools against a SystemExecutor instance.

    Memory tools (`remember`, `recall`) are registered only when a
    MemoryEngine is supplied. Imported lazily to avoid circular deps.
    """
    from .file_tools import register_file_tools
    from .system_tools import register_system_tools
    from .browser_tools import register_browser_tools
    from .vision_tools import register_vision_tools

    reg = ToolRegistry()
    register_file_tools(reg, executor)
    register_system_tools(reg, executor)
    register_browser_tools(reg)
    register_vision_tools(reg)
    if memory is not None:
        from .memory_tools import register_memory_tools
        register_memory_tools(reg, memory)
    return reg
