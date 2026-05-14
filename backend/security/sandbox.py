"""Sandbox helpers — utilities to keep risky ops contained."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..config import get_settings


def sandbox_path(*parts: str) -> Path:
    """Return a path inside the configured sandbox dir, creating it if needed."""
    root = Path(get_settings().sandbox_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    p = root.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def working_directory(path: str | Path) -> Iterator[Path]:
    """Temporarily chdir into `path` (used by safe shell helpers)."""
    import os
    prev = Path.cwd()
    target = Path(path).resolve()
    try:
        os.chdir(target)
        yield target
    finally:
        os.chdir(prev)
