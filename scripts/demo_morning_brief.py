"""
Demo workflow: "Morning brief".

Run with:  python -m scripts.demo_morning_brief

Steps:
  1. Get system status (tool: system_info)
  2. Search the web for "AI news today" (tool: web_search)
  3. Summarize everything into a 6-line morning brief (prompt step)
  4. Save it to data/sandbox/morning_brief.md (tool: write_file)

Requires:
  * ANTHROPIC_API_KEY set
  * `pip install -r requirements.txt`
  * `playwright install chromium` (one-time)
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdout on Windows so unicode (✓, ✗, emoji) doesn't crash cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.panel import Panel

from backend.api.deps import get_stack
from backend.config import get_settings
from backend.db.session import init_db
from backend.modules.workflow_engine import Step, Workflow

console = Console()


def build_workflow() -> Workflow:
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = str(Path(get_settings().sandbox_root).resolve() / f"brief_{today}.md")

    return Workflow(
        id="morning_brief",
        description="Daily 6-line morning brief.",
        steps=[
            Step(
                id="sys",
                kind="tool",
                tool="system_info",
                input={},
            ),
            Step(
                id="news",
                kind="tool",
                tool="web_search",
                input={"query": "top AI news today", "max_results": 5},
                optional=True,        # don't abort if browser isn't installed
            ),
            Step(
                id="brief",
                kind="prompt",
                prompt=(
                    "Write a crisp 6-line morning brief for today.\n"
                    "Source A (system status): ${sys}\n"
                    "Source B (news search): ${news}\n"
                    "Format: bullet points, max 12 words each."
                ),
            ),
            Step(
                id="save",
                kind="tool",
                tool="write_file",
                input={"path": out_path, "content": "${brief}", "overwrite": True},
            ),
        ],
    )


async def main() -> int:
    cfg = get_settings()
    if not cfg.anthropic_api_key:
        console.print("[red]ANTHROPIC_API_KEY not set in .env — abort.[/red]")
        return 1

    await init_db()
    stack = get_stack()

    console.print(Panel("[cyan]Scawward · Morning Brief Demo[/cyan]", expand=False))
    wf = build_workflow()
    outcomes = await stack.workflows.run(wf)

    for o in outcomes:
        color = "green" if o.ok else "red"
        snippet = (str(o.output) if o.ok else o.error or "")[:240]
        console.print(f"[{color}]{o.step_id:>8}[/{color}]  {snippet}")

    console.print(Panel("[green]Done.[/green] Check data/sandbox/ for the brief file."))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
