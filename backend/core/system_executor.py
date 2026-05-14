"""
SystemExecutor — the "hands" of Scawward.

Wraps OS-level primitives so that:
  * every action goes through one auditable choke-point;
  * paths are validated against the security policy;
  * exceptions become structured failures (never raw stack traces).

Tool functions live in `backend/tools/` and call back into this class.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from ..config import Settings, get_settings
from ..security.policy import PolicyEngine

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stdout": self.stdout[-2000:],
            "stderr": self.stderr[-2000:],
            "returncode": self.returncode,
            **(self.extra or {}),
        }


class SystemExecutor:
    def __init__(self, policy: PolicyEngine, settings: Settings | None = None) -> None:
        self.policy = policy
        self.cfg = settings or get_settings()

    # ─── Filesystem ───────────────────────────────────────────────
    async def read_file(self, path: str, max_bytes: int = 200_000) -> ExecResult:
        p = self._resolve_readable(path)
        if isinstance(p, ExecResult):
            return p
        try:
            data = await asyncio.to_thread(p.read_bytes)
            if len(data) > max_bytes:
                data = data[:max_bytes]
            text = data.decode("utf-8", errors="replace")
            return ExecResult(ok=True, stdout=text, extra={"path": str(p), "bytes": len(data)})
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    async def write_file(self, path: str, content: str, overwrite: bool = False) -> ExecResult:
        p = self._resolve_writable(path)
        if isinstance(p, ExecResult):
            return p
        if p.exists() and not overwrite:
            return ExecResult(ok=False, stderr=f"refusing to overwrite {p}")
        try:
            await asyncio.to_thread(p.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(p.write_text, content, "utf-8")
            return ExecResult(ok=True, stdout=f"wrote {len(content)} chars",
                              extra={"path": str(p)})
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    async def list_dir(self, path: str) -> ExecResult:
        p = self._resolve_readable(path)
        if isinstance(p, ExecResult):
            return p
        try:
            entries = []
            for child in sorted(p.iterdir()):
                entries.append({
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else None,
                })
            return ExecResult(ok=True, extra={"path": str(p), "entries": entries})
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    async def search_files(
        self,
        pattern: str,
        path: str,
        search_content: bool = False,
        file_extension: str | None = None,
        max_results: int = 50,
    ) -> ExecResult:
        """Recursive search for files by name or by content.

        - `search_content=False` (default): match `pattern` against filenames.
        - `search_content=True`: open each file and match `pattern` against lines.

        Skips noisy dirs (node_modules, .git, venv, __pycache__) and binary-ish
        files when scanning content. Caps results at `max_results`.
        """
        root = self._resolve_readable(path)
        if isinstance(root, ExecResult):
            return root
        if not root.is_dir():
            return ExecResult(ok=False, stderr=f"not a directory: {root}")

        SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv",
                     "dist", "build", ".next", "target"}
        needle = pattern.lower()
        results: list[dict[str, Any]] = []

        def _walk() -> list[dict[str, Any]]:
            hits: list[dict[str, Any]] = []
            for r, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs
                           if d not in SKIP_DIRS and not d.startswith(".")]
                for fname in files:
                    if len(hits) >= max_results:
                        return hits
                    if file_extension and not fname.lower().endswith(file_extension.lower()):
                        continue
                    fpath = os.path.join(r, fname)
                    if not search_content:
                        if needle in fname.lower():
                            hits.append({
                                "path": fpath,
                                "name": fname,
                                "match_type": "filename",
                            })
                        continue
                    try:
                        # Skip > 2MB to avoid loading giant files.
                        if os.path.getsize(fpath) > 2_000_000:
                            continue
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            for i, line in enumerate(f, 1):
                                if needle in line.lower():
                                    hits.append({
                                        "path": fpath,
                                        "name": fname,
                                        "line": i,
                                        "snippet": line.strip()[:200],
                                        "match_type": "content",
                                    })
                                    if len(hits) >= max_results:
                                        return hits
                                    break  # one hit per file is enough
                    except (OSError, UnicodeDecodeError):
                        continue
            return hits

        try:
            results = await asyncio.to_thread(_walk)
            return ExecResult(
                ok=True,
                stdout=f"{len(results)} match(es) for {pattern!r}",
                extra={
                    "pattern": pattern,
                    "base_path": str(root),
                    "count": len(results),
                    "results": results,
                    "truncated": len(results) >= max_results,
                },
            )
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    async def move(self, src: str, dst: str) -> ExecResult:
        s = self._resolve_writable(src)
        d = self._resolve_writable(dst)
        for r in (s, d):
            if isinstance(r, ExecResult):
                return r
        try:
            await asyncio.to_thread(shutil.move, str(s), str(d))
            return ExecResult(ok=True, stdout=f"moved {s} → {d}")
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    async def delete(self, path: str) -> ExecResult:
        p = self._resolve_writable(path)
        if isinstance(p, ExecResult):
            return p
        try:
            if p.is_dir():
                await asyncio.to_thread(shutil.rmtree, p)
            else:
                await asyncio.to_thread(p.unlink)
            return ExecResult(ok=True, stdout=f"deleted {p}")
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    # ─── Processes / apps ─────────────────────────────────────────
    async def launch_app(self, command: str, args: list[str] | None = None,
                         cwd: str | None = None) -> ExecResult:
        decision = await self.policy.evaluate("launch_app", {"command": command})
        if not decision.allowed:
            return ExecResult(ok=False, stderr=f"blocked: {decision.reason}")
        try:
            proc = subprocess.Popen(
                [command, *(args or [])],
                cwd=cwd or None,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            return ExecResult(ok=True, stdout=f"launched pid={proc.pid}",
                              extra={"pid": proc.pid})
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    async def list_processes(self, name_filter: str | None = None) -> ExecResult:
        try:
            out = []
            for p in psutil.process_iter(["pid", "name", "username"]):
                info = p.info
                if name_filter and name_filter.lower() not in (info.get("name") or "").lower():
                    continue
                out.append(info)
            return ExecResult(ok=True, extra={"processes": out[:200]})
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    async def shell(self, command: str, timeout: float = 30.0) -> ExecResult:
        decision = await self.policy.evaluate("shell", {"command": command})
        if not decision.allowed:
            return ExecResult(ok=False, stderr=f"blocked: {decision.reason}")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return ExecResult(
                ok=proc.returncode == 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                returncode=proc.returncode,
            )
        except asyncio.TimeoutError:
            return ExecResult(ok=False, stderr="timeout")
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    # ─── System info ──────────────────────────────────────────────
    async def system_info(self) -> ExecResult:
        try:
            info = {
                "platform": sys.platform,
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage(os.path.expanduser("~")).percent,
                "process_count": len(psutil.pids()),
            }
            return ExecResult(ok=True, extra=info)
        except Exception as e:
            return ExecResult(ok=False, stderr=repr(e))

    # ─── Path safety helpers ──────────────────────────────────────
    def _resolve_readable(self, path: str) -> Path | ExecResult:
        p = self._resolve(path)
        if self._is_blocked(p):
            return ExecResult(ok=False, stderr=f"path blocked: {p}")
        return p

    def _resolve_writable(self, path: str) -> Path | ExecResult:
        p = self._resolve(path)
        if self._is_blocked(p):
            return ExecResult(ok=False, stderr=f"path blocked: {p}")
        if not self._is_allowed(p):
            return ExecResult(
                ok=False,
                stderr=f"write outside allowed roots: {p}",
            )
        return p

    @staticmethod
    def _resolve(path: str) -> Path:
        return Path(path).expanduser().resolve()

    def _is_blocked(self, p: Path) -> bool:
        return any(self._is_subpath(p, root) for root in self.cfg.blocked_path_list)

    def _is_allowed(self, p: Path) -> bool:
        roots = self.cfg.allowed_path_list
        if not roots:
            # Permissive default: only the sandbox dir.
            roots = [Path(self.cfg.sandbox_root).resolve()]
        return any(self._is_subpath(p, root) for root in roots)

    @staticmethod
    def _is_subpath(child: Path, parent: Path) -> bool:
        try:
            child.relative_to(parent.resolve())
            return True
        except ValueError:
            return False
