"""Pytest fixtures shared across the suite."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
import pytest_asyncio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def fake_executor() -> Any:
    """A SystemExecutor stub that records calls instead of touching the OS."""
    class _Stub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []

        async def read_file(self, path: str) -> Any:
            from backend.core.system_executor import ExecResult
            self.calls.append(("read_file", {"path": path}))
            return ExecResult(ok=True, stdout=f"<fake content of {path}>")

        async def write_file(self, path: str, content: str, overwrite: bool = False) -> Any:
            from backend.core.system_executor import ExecResult
            self.calls.append(("write_file", {"path": path, "len": len(content)}))
            return ExecResult(ok=True, stdout=f"wrote {path}")

        async def list_dir(self, path: str) -> Any:
            from backend.core.system_executor import ExecResult
            self.calls.append(("list_dir", {"path": path}))
            return ExecResult(ok=True, extra={"entries": []})

        async def system_info(self) -> Any:
            from backend.core.system_executor import ExecResult
            return ExecResult(ok=True, extra={"cpu_percent": 1.0})

    return _Stub()
