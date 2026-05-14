"""
Pre-flight check for Scawward.

Run this BEFORE the CLI to catch config issues fast, instead of debugging
inside an interactive prompt.

Cost: ~10 tokens (≈ $0.00003) when the API call succeeds.

Run with:  python -m scripts.check_setup
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows so unicode (✓, ✗, emoji) doesn't crash cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.table import Table

console = Console()


def _row(table: Table, label: str, ok: bool, detail: str) -> None:
    mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
    table.add_row(mark, label, detail)


async def main() -> int:
    from backend.api.deps import get_stack
    from backend.config import get_settings

    cfg = get_settings()
    table = Table(title="Scawward · Pre-flight check", show_header=False, expand=True)
    table.add_column(width=3)
    table.add_column(min_width=22)
    table.add_column()

    issues = 0

    # 1. API key present + not the placeholder
    key_ok = bool(cfg.anthropic_api_key) and "xxxx" not in cfg.anthropic_api_key
    _row(table, "ANTHROPIC_API_KEY",
         key_ok,
         f"set ({cfg.anthropic_api_key[:10]}…)" if key_ok else "missing or placeholder")
    if not key_ok:
        issues += 1

    # 2. Sandbox dir exists
    sb = Path(cfg.sandbox_root).resolve()
    sb_ok = sb.exists()
    _row(table, "Sandbox dir", sb_ok, str(sb))
    if not sb_ok:
        issues += 1

    # 3. Allowed paths exist
    allowed = cfg.allowed_path_list
    allowed_ok = bool(allowed) and all(p.exists() for p in allowed)
    detail = ", ".join(str(p) for p in allowed) or "(empty → sandbox-only)"
    _row(table, "Allowed paths", allowed_ok, detail)

    # 4. DB writable
    try:
        from backend.db.session import init_db
        await init_db()
        _row(table, "Database init", True, cfg.db_url)
    except Exception as e:
        _row(table, "Database init", False, repr(e))
        issues += 1

    # 5. App stack builds (loads chromadb, registers tools)
    try:
        stack = get_stack()
        _row(table, "App stack", True, f"{len(stack.tools.names())} tools registered")
    except Exception as e:
        _row(table, "App stack", False, repr(e))
        issues += 1

    # 6. Tiny Claude round-trip ("say hi" — 10 tokens-ish)
    if key_ok:
        try:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=cfg.anthropic_api_key)
            msg = await client.messages.create(
                model=cfg.fast_model,        # cheap model for the smoke test
                max_tokens=20,
                messages=[{"role": "user", "content": "Reply with just: ok"}],
            )
            text = "".join(b.text for b in msg.content if b.type == "text").strip()
            _row(table, "Claude API call",
                 bool(text),
                 f"model={cfg.fast_model} · reply={text!r} · "
                 f"in={msg.usage.input_tokens}t out={msg.usage.output_tokens}t")
        except Exception as e:
            _row(table, "Claude API call", False, repr(e))
            issues += 1

    console.print(table)

    if issues:
        console.print(f"\n[red]{issues} issue(s) — fix .env before running the CLI.[/red]")
        return 1
    console.print("\n[green]All green. You can now run:  python -m scripts.scawward_cli[/green]")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
