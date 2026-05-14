import pytest

from backend.security.policy import PolicyEngine


@pytest.mark.asyncio
async def test_dangerous_shell_blocked() -> None:
    p = PolicyEngine()
    d = await p.evaluate("shell", {"command": "rm -rf /"})
    assert not d.allowed


@pytest.mark.asyncio
async def test_safe_shell_allowed() -> None:
    p = PolicyEngine()
    d = await p.evaluate("shell", {"command": "echo hello"})
    assert d.allowed


@pytest.mark.asyncio
async def test_delete_requires_confirmation() -> None:
    p = PolicyEngine()
    d = await p.evaluate("delete_file", {"path": "x"})
    assert d.allowed
    assert d.requires_confirmation
