"""Tests for SystemExecutor.search_files and the matching agent tool."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.system_executor import SystemExecutor
from backend.security.policy import PolicyEngine
from backend.tools.file_tools import register_file_tools
from backend.tools.registry import ToolRegistry


@pytest.fixture
def executor(tmp_path: Path, monkeypatch) -> SystemExecutor:
    """Real executor wired to a temp sandbox so paths resolve cleanly."""
    from backend.config import get_settings

    cfg = get_settings()
    # Allow tmp_path so search_files passes the readable check.
    monkeypatch.setattr(cfg, "allowed_paths", str(tmp_path), raising=False)
    return SystemExecutor(PolicyEngine(), settings=cfg)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A small file tree we can search through."""
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "todo.md").write_text("- [ ] write tests\n- [ ] ship\n")
    (tmp_path / "notes" / "ideas.md").write_text("Nothing here\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "# TODO: refactor\n"
        "def main():\n"
        "    pass\n"
    )
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    pass\n")
    # noisy dir that must be skipped
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "trash.py").write_text("# TODO: should be skipped\n")
    return tmp_path


@pytest.mark.asyncio
async def test_search_files_by_filename(executor: SystemExecutor, workspace: Path) -> None:
    r = await executor.search_files(pattern="todo", path=str(workspace))
    assert r.ok, r.stderr
    names = {hit["name"] for hit in r.extra["results"]}
    assert "todo.md" in names
    # node_modules/trash.py contains "todo" in *content*, not name; should not show up.
    assert "trash.py" not in names


@pytest.mark.asyncio
async def test_search_files_by_content(executor: SystemExecutor, workspace: Path) -> None:
    r = await executor.search_files(
        pattern="TODO", path=str(workspace), search_content=True,
    )
    assert r.ok
    paths = {Path(hit["path"]).name for hit in r.extra["results"]}
    assert "todo.md" in paths or "main.py" in paths
    # noisy dir must be skipped even when grepping content
    assert "trash.py" not in paths


@pytest.mark.asyncio
async def test_search_files_extension_filter(executor: SystemExecutor, workspace: Path) -> None:
    r = await executor.search_files(
        pattern="def", path=str(workspace),
        search_content=True, file_extension=".py",
    )
    assert r.ok
    for hit in r.extra["results"]:
        assert hit["path"].endswith(".py")


@pytest.mark.asyncio
async def test_search_files_blocked_outside_sandbox(
    executor: SystemExecutor, tmp_path: Path, monkeypatch
) -> None:
    """Searching from a path that is NOT a subpath of any allowed root must fail
    if the policy declared the path as blocked."""
    # tmp_path is allowed via fixture; pick a sibling we explicitly *block*.
    blocked = tmp_path.parent
    monkeypatch.setattr(executor.cfg, "blocked_paths", str(blocked), raising=False)

    r = await executor.search_files(pattern="x", path=str(blocked))
    assert not r.ok
    assert "blocked" in r.stderr.lower()


@pytest.mark.asyncio
async def test_tool_registration_and_call(executor: SystemExecutor, workspace: Path) -> None:
    reg = ToolRegistry()
    register_file_tools(reg, executor)

    out = await reg.execute("search_files", {
        "pattern": "main",
        "path": str(workspace),
    })
    assert out.ok, out.summary
    assert "results" in out.data
    found = {Path(h["path"]).name for h in out.data["results"]}
    assert "main.py" in found
