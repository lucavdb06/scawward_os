"""
FileManager — smart file organization helpers.

These are *not* tools the agent calls directly; they're higher-level
operations the agent can invoke via the workflow engine, e.g.:
"organize my Downloads folder by type / by date / by project".
"""
from __future__ import annotations

import logging
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


CATEGORY_BY_EXT: dict[str, str] = {
    # Docs
    "pdf": "Documents", "docx": "Documents", "doc": "Documents",
    "odt": "Documents", "txt": "Documents", "md": "Documents",
    # Sheets
    "xlsx": "Spreadsheets", "csv": "Spreadsheets", "ods": "Spreadsheets",
    # Slides
    "pptx": "Presentations", "key": "Presentations",
    # Images
    "png": "Images", "jpg": "Images", "jpeg": "Images",
    "gif": "Images", "svg": "Images", "webp": "Images",
    # Video / audio
    "mp4": "Videos", "mov": "Videos", "mkv": "Videos", "webm": "Videos",
    "mp3": "Audio", "wav": "Audio", "flac": "Audio",
    # Archives
    "zip": "Archives", "tar": "Archives", "gz": "Archives", "7z": "Archives",
    # Code
    "py": "Code", "js": "Code", "ts": "Code", "rs": "Code", "go": "Code",
    "java": "Code", "cpp": "Code", "c": "Code", "html": "Code",
    # Installers
    "exe": "Installers", "msi": "Installers", "dmg": "Installers",
}


class FileManager:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    # ─── Organization strategies ──────────────────────────────────
    def plan_by_type(self) -> dict[str, list[Path]]:
        """Return a {category_dir: [files]} plan WITHOUT moving anything yet."""
        plan: dict[str, list[Path]] = defaultdict(list)
        for f in self._iter_files():
            cat = CATEGORY_BY_EXT.get(f.suffix.lower().lstrip("."), "Other")
            plan[cat].append(f)
        return dict(plan)

    def plan_by_date(self) -> dict[str, list[Path]]:
        plan: dict[str, list[Path]] = defaultdict(list)
        for f in self._iter_files():
            ts = datetime.fromtimestamp(f.stat().st_mtime)
            plan[ts.strftime("%Y-%m")].append(f)
        return dict(plan)

    # ─── Apply plan ───────────────────────────────────────────────
    def apply_plan(self, plan: dict[str, list[Path]], *, dry_run: bool = True) -> list[str]:
        actions: list[str] = []
        for subdir, files in plan.items():
            target_dir = self.root / subdir
            for f in files:
                dst = target_dir / f.name
                actions.append(f"{'[dry] ' if dry_run else ''}{f} → {dst}")
                if not dry_run:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(dst))
        return actions

    # ─── Search ───────────────────────────────────────────────────
    def find(self, pattern: str, *, recursive: bool = True) -> list[Path]:
        glob = self.root.rglob if recursive else self.root.glob
        return list(glob(pattern))

    # ─── Internals ────────────────────────────────────────────────
    def _iter_files(self) -> Iterable[Path]:
        for child in self.root.iterdir():
            if child.is_file():
                yield child
