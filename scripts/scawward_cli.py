"""
Tiny terminal CLI for Scawward — chat without spinning up the web UI.

Run with:  python -m scripts.scawward_cli
"""
from __future__ import annotations

import asyncio
import sys

# Force UTF-8 stdout on Windows so unicode (✓, ✗, emoji) doesn't crash cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.prompt import Prompt

from backend.api.deps import get_stack
from backend.config import get_settings
from backend.db.session import init_db


async def main() -> None:
    if not get_settings().anthropic_api_key:
        Console().print("[red]ANTHROPIC_API_KEY missing in .env[/red]")
        return

    await init_db()
    stack = get_stack()
    console = Console()
    console.print("[cyan]Scawward CLI · type /quit to exit[/cyan]")

    while True:
        try:
            text = Prompt.ask("[bold cyan]you[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            break
        if text.strip() in {"/quit", "/exit"}:
            break
        buf = ""
        with Live(Markdown(""), console=console, refresh_per_second=12) as live:
            async for ev in stack.commands.stream(text):
                if ev["type"] == "text":
                    buf += ev["text"]
                    live.update(Markdown(buf))
                elif ev["type"] == "tool":
                    console.print(f"[magenta]🔧 {ev['name']}[/magenta] {ev['input']}")


if __name__ == "__main__":
    asyncio.run(main())
