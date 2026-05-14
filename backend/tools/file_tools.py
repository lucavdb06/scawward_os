"""File-system tools exposed to the agent."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .registry import ToolRegistry, ToolResult

if TYPE_CHECKING:
    from ..core.system_executor import SystemExecutor


def register_file_tools(reg: ToolRegistry, executor: "SystemExecutor") -> None:

    @reg.tool(
        name="read_file",
        description="Read a UTF-8 text file. Use for inspecting code, configs, notes.",
        schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
    async def _read(path: str) -> ToolResult:
        r = await executor.read_file(path)
        return ToolResult(ok=r.ok, summary=r.stderr or f"read {path}", data=r.to_dict())

    @reg.tool(
        name="write_file",
        description=(
            "Create or update a UTF-8 text file. Set overwrite=true to replace "
            "existing content (will require user confirmation)."
        ),
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean"},
            },
            "required": ["path", "content"],
        },
    )
    async def _write(path: str, content: str, overwrite: bool = False) -> ToolResult:
        r = await executor.write_file(path, content, overwrite=overwrite)
        return ToolResult(ok=r.ok, summary=r.stdout or r.stderr, data=r.to_dict())

    @reg.tool(
        name="list_dir",
        description="List the contents of a directory.",
        schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
    async def _ls(path: str) -> ToolResult:
        r = await executor.list_dir(path)
        return ToolResult(ok=r.ok, summary=f"listed {path}", data=r.to_dict())

    @reg.tool(
        name="move_path",
        description="Move or rename a file/directory.",
        schema={
            "type": "object",
            "properties": {"src": {"type": "string"}, "dst": {"type": "string"}},
            "required": ["src", "dst"],
        },
    )
    async def _mv(src: str, dst: str) -> ToolResult:
        r = await executor.move(src, dst)
        return ToolResult(ok=r.ok, summary=r.stdout or r.stderr, data=r.to_dict())

    @reg.tool(
        name="search_files",
        description=(
            "Recursively find files inside a directory. Two modes: "
            "`search_content=false` (default) matches `pattern` against "
            "filenames; `search_content=true` searches inside files. "
            "Skips noisy folders (node_modules, .git, venv, __pycache__). "
            "Use when the user asks 'find all .py files with TODO' or "
            "'where is config.json on my disk'."
        ),
        schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Substring to match (case-insensitive).",
                },
                "path": {
                    "type": "string",
                    "description": "Root directory to search from.",
                },
                "search_content": {
                    "type": "boolean",
                    "description": "If true, grep inside files; if false, match filenames.",
                },
                "file_extension": {
                    "type": "string",
                    "description": "Optional filter: only files ending with this (e.g. '.py').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Cap on number of results (default 50, max 200).",
                },
            },
            "required": ["pattern", "path"],
        },
    )
    async def _find(
        pattern: str,
        path: str,
        search_content: bool = False,
        file_extension: str | None = None,
        max_results: int = 50,
    ) -> ToolResult:
        max_results = max(1, min(int(max_results), 200))
        r = await executor.search_files(
            pattern=pattern,
            path=path,
            search_content=search_content,
            file_extension=file_extension,
            max_results=max_results,
        )
        return ToolResult(ok=r.ok, summary=r.stdout or r.stderr, data=r.to_dict())

    @reg.tool(
        name="delete_file",
        description="Delete a file or directory (requires confirmation).",
        schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
    async def _rm(path: str) -> ToolResult:
        r = await executor.delete(path)
        return ToolResult(ok=r.ok, summary=r.stdout or r.stderr, data=r.to_dict())
