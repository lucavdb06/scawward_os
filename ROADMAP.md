# Scawward — Phase 1 Roadmap

> 4 weeks, solo, tight budget. Each week ends with a *demoable* milestone.

## Week 1 — MVP loop

**Goal:** typed command → Claude → tool call → real action on disk.

- [x] Project skeleton, `.env`, requirements
- [x] `EventBus`, `PolicyEngine`, `SystemExecutor`
- [x] `ToolRegistry` + file & system tools
- [x] `ScawwardAgent` with tool-use loop and prompt caching
- [x] FastAPI `/api/command` + `/api/health`
- [x] CLI: `python -m scripts.scawward_cli`
- [x] Tests: event bus, policy, registry

**Milestone (testable):**
```
You: "Create a file named todo.md in my sandbox with three priorities for tomorrow."
Scawward: <calls write_file once, replies with confirmation>
```

Verify: file exists, `tool_executions` has the row, audit log clean.

---

## Week 2 — Intelligence: memory + vision + browser

**Goal:** Scawward *remembers* and *sees*.

- [x] SQLAlchemy models + async session
- [x] ChromaDB vector store
- [x] `MemoryEngine.remember` after every action; `recall` injected before reply
- [x] Vision module: capture + Claude vision describe
- [x] Browser controller: search + read URL
- [x] Browser tools and vision tools registered
- [x] Wire `recall` into `ScawwardAgent.stream` (auto-injected as a `<long_term_memory>` system block + `remember`/`recall` tools exposed to Claude)
- [ ] Background `vision.watch()` task started by lifespan

**Milestone:**
```
You: "What's on my screen and what was I asking you about earlier?"
Scawward: <calls screenshot, recalls last few interactions, answers>
```

---

## Week 3 — Workflows + UI + WebSocket streaming

**Goal:** multi-step plans run autonomously; real chat UI.

- [x] `WorkflowEngine` with prompt/tool/python steps and `${var}` interp
- [x] `/api/workflows/run` REST + persistence in DB
- [x] WebSocket `/ws/chat` streaming + `/ws/events` debug feed
- [x] React UI: chat + event sidebar
- [x] WebSocket auto-reconnect with exponential backoff
- [x] Markdown rendering in chat + tool result cards
- [x] **Pluggable LLM providers** (`anthropic` + `ollama`) — local GPU mode for free, offline, unlimited iteration
- [ ] UI toggle for provider/model switch (currently env-var only)
- [ ] Save/load workflows from UI
- [ ] Confirmation prompts in UI for `requires_confirmation` decisions
- [ ] Conversation persistence across reloads

**Milestone:**
```
You: "Write me my morning brief and save it."
Scawward: runs the morning_brief workflow, streams progress, leaves a markdown
          file in the sandbox.
```
(see `scripts/demo_morning_brief.py`)

---

## Week 4 — Polish, perf, packaging

**Goal:** something you can show without apologizing.

- [ ] Token meter wired into `/api/health` and the UI top bar
- [ ] Switch heavy short tasks to `claude-haiku-4-5` (model tiering)
- [ ] Parallel tool execution where the LLM emits multiple `tool_use`
- [ ] App launcher: Start Menu indexing + fuzzy search wired into a tool
- [ ] File manager: "organize Downloads by type" workflow
- [ ] Logging: structured JSON logs to `data/logs/scawward.jsonl`
- [ ] PyInstaller-packaged single binary for the backend
- [ ] Quick screen-recorded demo: 60-second "what Scawward does for you"

**Milestone:**
- Cold start to first usable response < 3 s.
- A 3-step workflow finishes in < 12 s on a typical laptop.
- Total monthly API cost on personal use < target you set in `.env`.

---

## Backlog (Phase 1.5 / Phase 2 prep)

- Voice in/out (Whisper-style STT + ElevenLabs / Cartesia TTS)
- Holographic UI (Three.js + WebGPU prototype)
- Multi-agent: planner / worker split
- Cross-machine memory (encrypted sync)
- Plugin system: drop a Python file in `plugins/` → tool auto-registers
- Mobile companion app (read-only first, then voice trigger)
