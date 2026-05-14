"""
AppLauncher — find and launch installed applications by friendly name.

Cross-platform-ish strategy:
  * Windows: scan the Start Menu for `.lnk` files and the registry App Paths.
  * macOS:   scan /Applications and ~/Applications.
  * Linux:   parse .desktop files in standard XDG dirs.

For Phase 1 we ship Windows + simple PATH lookup. macOS/Linux are TODO stubs.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppEntry:
    name: str
    path: Path
    score: float = 0.0


class AppLauncher:
    def __init__(self) -> None:
        self._index: list[AppEntry] = []
        self._loaded = False

    def refresh(self) -> int:
        self._index = list(self._discover())
        self._loaded = True
        return len(self._index)

    def find(self, query: str, limit: int = 5) -> list[AppEntry]:
        if not self._loaded:
            self.refresh()
        q = query.lower().strip()
        scored: list[AppEntry] = []
        for app in self._index:
            n = app.name.lower()
            if q == n:
                score = 1.0
            elif n.startswith(q):
                score = 0.8
            elif q in n:
                score = 0.5
            else:
                continue
            scored.append(AppEntry(app.name, app.path, score))
        scored.sort(key=lambda a: a.score, reverse=True)
        return scored[:limit]

    # ─── Discovery ────────────────────────────────────────────────
    def _discover(self) -> list[AppEntry]:
        if sys.platform == "win32":
            return self._discover_windows()
        if sys.platform == "darwin":
            return self._discover_macos()
        return self._discover_linux()

    def _discover_windows(self) -> list[AppEntry]:
        roots = [
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        out: list[AppEntry] = []
        for root in roots:
            if not root.exists():
                continue
            for lnk in root.rglob("*.lnk"):
                out.append(AppEntry(name=lnk.stem, path=lnk))
        return out

    def _discover_macos(self) -> list[AppEntry]:
        out: list[AppEntry] = []
        for root in (Path("/Applications"), Path.home() / "Applications"):
            if not root.exists():
                continue
            for app in root.glob("*.app"):
                out.append(AppEntry(name=app.stem, path=app))
        return out

    def _discover_linux(self) -> list[AppEntry]:
        out: list[AppEntry] = []
        for root in (Path("/usr/share/applications"),
                     Path.home() / ".local/share/applications"):
            if not root.exists():
                continue
            for desktop in root.glob("*.desktop"):
                out.append(AppEntry(name=desktop.stem, path=desktop))
        return out
