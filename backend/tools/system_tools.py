"""System / process tools."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .registry import ToolRegistry, ToolResult

if TYPE_CHECKING:
    from ..core.system_executor import SystemExecutor


def register_system_tools(reg: ToolRegistry, executor: "SystemExecutor") -> None:

    @reg.tool(
        name="launch_app",
        description=(
            "Start a desktop application by executable path or name. "
            "Returns immediately with the new PID."
        ),
        schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
                "cwd": {"type": "string"},
            },
            "required": ["command"],
        },
    )
    async def _launch(command: str, args: list[str] | None = None,
                      cwd: str | None = None) -> ToolResult:
        r = await executor.launch_app(command, args=args, cwd=cwd)
        return ToolResult(ok=r.ok, summary=r.stdout or r.stderr, data=r.to_dict())

    @reg.tool(
        name="list_processes",
        description="List currently running processes (optionally filter by name).",
        schema={
            "type": "object",
            "properties": {"name_filter": {"type": "string"}},
        },
    )
    async def _ps(name_filter: str | None = None) -> ToolResult:
        r = await executor.list_processes(name_filter=name_filter)
        return ToolResult(ok=r.ok, summary=f"{len((r.extra or {}).get('processes', []))} procs",
                          data=r.to_dict())

    @reg.tool(
        name="shell",
        description=(
            "Run a shell command. Dangerous commands (rm -rf, format, etc.) "
            "are blocked. Network commands require confirmation."
        ),
        schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["command"],
        },
    )
    async def _sh(command: str, timeout: float = 30.0) -> ToolResult:
        r = await executor.shell(command, timeout=timeout)
        return ToolResult(ok=r.ok, summary=(r.stdout or r.stderr)[:300], data=r.to_dict())

    @reg.tool(
        name="system_info",
        description="Quick health check of the host machine (CPU, memory, disk).",
        schema={"type": "object", "properties": {}},
    )
    async def _info() -> ToolResult:
        r = await executor.system_info()
        return ToolResult(ok=r.ok, summary="system metrics", data=r.to_dict())
