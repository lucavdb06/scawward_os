# Scawward

> An AI-piloted operating layer.
> Phase 1: a fluid, deeply intelligent digital OS.
> Phase 2: holographic Iron-Man-style interface.

Scawward is **not** a kernel — it's a thin agentic layer on top of your existing
OS that lets a single LLM (Claude) drive your computer through a controlled
set of tools: files, apps, browser, screen capture, shell, workflows.

```
┌─────────────────────────────────────────────────────────────┐
│  React UI  ◀──WS──▶  FastAPI  ◀──▶  ScawwardAgent (Claude)  │
│                          │              │                   │
│                          ▼              ▼                   │
│                     EventBus  ◀──▶  ToolRegistry            │
│                          │              │                   │
│                          ▼              ▼                   │
│        Memory  Context  Vision  SystemExecutor (PC)         │
│           │       │       │            │                    │
│        Chroma  in-mem   Claude     fs/proc/shell/browser    │
│         + SQL                                               │
└─────────────────────────────────────────────────────────────┘
```

## Quick start

```powershell
# 1. Python deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium                # one-time, for browser tools

# 2. Config
copy .env.example .env
# → put your ANTHROPIC_API_KEY in .env
# → set SCAWWARD_ALLOWED_PATHS to dirs Scawward can write into

# 3. Run the backend
python -m backend.main
# → http://127.0.0.1:8765/docs

# 4. (optional) Frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## Try it

Quick CLI chat:
```powershell
python -m scripts.scawward_cli
```

Full demo workflow (system info + web search + summary file):
```powershell
python -m scripts.demo_morning_brief
```

Run the tests:
```powershell
pytest -q
```

## Project layout

```
backend/
  core/              the brain, executor, memory, context, event bus
  modules/           features: command, vision, files, apps, browser, workflow
  tools/             function-calling tools (= Claude's hands)
  api/               FastAPI routes + WebSocket + Pydantic schemas
  db/                SQLAlchemy models + Chroma vector store
  security/          policy engine + sandbox
  utils/             token meter, helpers
frontend/            Vite + React + TypeScript chat UI
tests/               pytest suite
scripts/             demos and CLI
data/                runtime data (db, vector index, sandbox)
```

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for a deep dive and
[`ROADMAP.md`](./ROADMAP.md) for the week-by-week plan.

## Safety, briefly

- Every action goes through `PolicyEngine` (deny / confirm / allow).
- Filesystem writes are restricted to `SCAWWARD_ALLOWED_PATHS`.
- `SCAWWARD_BLOCKED_PATHS` is always blocked, even for reads.
- Dangerous shell patterns (`rm -rf`, `format`, `shutdown`, `dd if=`, …) are
  blocked at the policy layer before they hit the executor.
- An audit log of every tool call lives in `tool_executions` (SQL).

## Status

This is **Phase 1 scaffolding**. Everything compiles and tests pass without an
API key; with a key you get a working agentic loop, prompt caching, vision,
browser automation, persistent memory, and a streaming web UI.
