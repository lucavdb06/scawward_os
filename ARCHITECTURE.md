# Scawward — Architecture (Phase 1)

> Goal: a single LLM acts as the conductor of your computer. Everything else
> is plumbing that lets it perceive, decide, act, remember, and recover.

## 1. System design

### 1.1 The agentic loop

```
        ┌────────────┐
USER ──▶│  UI / CLI  │──▶ text
        └────────────┘
              │
              ▼
        ┌──────────────────┐    inject system prompt + context + memory + tools
        │ CommandProcessor │──────────────────────────────────────────┐
        └──────────────────┘                                          │
              │                                                       ▼
              ▼                                             ┌──────────────────┐
        ┌────────────────┐  messages.create()               │   Claude API     │
        │ ScawwardAgent  │ ─────────────────────────────────▶                  │
        └────────────────┘  ◀── content[blocks] ────────────│   (tools)        │
              │                                             └──────────────────┘
              │   if any tool_use:
              │       ▼
              │   ┌──────────────┐    schema-validated input
              │   │ ToolRegistry │ ──────────────────────────▶ SystemExecutor
              │   └──────────────┘    ◀── ExecResult ──────────────┘
              │   loop ↑ until stop_reason != "tool_use"
              ▼
        text + trace ──▶ stream back to UI via WebSocket
              │
              ├──▶ MemoryEngine.remember(action)
              ├──▶ EventBus.emit(executor.action.done)
              └──▶ ContextManager (updated)
```

The loop is **bounded** (`MAX_TOOL_ITERATIONS = 8`) so a confused agent can't
spin forever. Each iteration is logged for audit and replay.

### 1.2 How "the AI controls everything"

Three principles keep this from becoming chaos:

1. **One choke point**: every side-effect goes through `SystemExecutor`. The
   agent never touches `os`, `subprocess`, `requests`, etc., directly.
2. **Declarative tools**: each capability is a registered tool with a JSON
   schema. The agent gets exactly the surface area we expose — no more.
3. **Policy gate**: before any tool runs, `PolicyEngine.evaluate(tool, input)`
   returns `ALLOW`, `CONFIRM`, or `DENY`. Adding a new safety rule is one
   function.

### 1.3 End-to-end data flow (chat command)

```
  WebSocket text
      │
      ▼
  CommandProcessor.stream(text)
      │  emits  command.received
      ▼
  ScawwardAgent.stream()
      │  build messages = working_memory + new_user_turn
      │  build system  = SYSTEM_PROMPT (cached) + context.serialize_for_llm()
      │  build tools   = ToolRegistry.schema_for_anthropic()
      │
      │  Anthropic.messages.create(...)
      │      → text blocks            → yield {type: "text"}
      │      → tool_use blocks        → for each: PolicyEngine.evaluate
      │                                            ToolRegistry.execute
      │                                            EventBus.emit(executor.action.done)
      │                                            MemoryEngine.remember(action)
      │      → tool_result blocks back into messages, loop
      │
      ▼
  yield {type: "done"}
      │
      ▼
  UI renders incremental text + 🔧 tool chips
```

### 1.4 Critical components

| Component        | Role                                | Cost-of-change |
|------------------|-------------------------------------|----------------|
| `ScawwardAgent`  | LLM loop, tool dispatch, streaming  | High — lives at the center |
| `SystemExecutor` | The only thing that touches the OS  | Medium |
| `ToolRegistry`   | LLM ⇄ Python boundary               | Low — pure glue |
| `PolicyEngine`   | Safety gate                         | Low |
| `MemoryEngine`   | Working / episodic / semantic       | Medium |
| `ContextManager` | Real-time grounding                 | Low |
| `EventBus`       | Async pub/sub, decouples modules    | Very low |
| `WorkflowEngine` | Multi-step deterministic plans      | Low |

### 1.5 Interaction patterns

- **Reactive** (default): user → command → agent → answer.
- **Proactive** (later): EventBus listens for `vision.window.changed`, pattern
  matches, and the agent volunteers help.
- **Workflow** (saved scripts): `WorkflowEngine` runs a recipe of prompts
  and tool calls with template-string variable passing (`${step_id}`).

---

## 2. Core components — implementation pointers

| File | What to read first |
|---|---|
| `backend/core/scawward_agent.py` | `ScawwardAgent.stream()` — the agentic loop. |
| `backend/core/system_executor.py` | Path safety helpers + each method. |
| `backend/core/memory_engine.py` | `remember` / `recall` policy. |
| `backend/core/context_manager.py` | `serialize_for_llm` shape. |
| `backend/core/event_bus.py` | Glob subscriptions, `recent()` audit. |
| `backend/tools/registry.py` | Anthropic schema converter. |
| `backend/tools/*.py` | One file per tool family. |
| `backend/security/policy.py` | Default rules; add yours here. |

---

## 3. Feature priority (Phase 1)

| # | Feature | Owner module | Status |
|---|---|---|---|
| a | Command Processor      | `modules/command_processor.py` | ✅ |
| b | Vision Module          | `modules/vision.py` + `tools/vision_tools.py` | ✅ |
| c | File Management        | `modules/file_manager.py` + `tools/file_tools.py` | ✅ |
| d | App Launcher           | `modules/app_launcher.py` + `tools/system_tools.py` | ✅ |
| e | Browser Control        | `modules/browser_control.py` + `tools/browser_tools.py` | ✅ |
| f | Workflow Engine        | `modules/workflow_engine.py` | ✅ |

---

## 4. API design

### 4.1 REST (`/api`)

| Method | Path                   | Body / Query                      | Returns |
|--------|------------------------|-----------------------------------|---------|
| GET    | `/api/health`          | —                                 | `HealthResponse` |
| POST   | `/api/command`         | `CommandRequest`                  | `CommandResponse` |
| POST   | `/api/memory/recall`   | `MemoryQuery`                     | `list[MemoryHit]` |
| POST   | `/api/workflows/run`   | `WorkflowSpec`                    | `list[StepOutcomeOut]` |
| GET    | `/api/tools`           | —                                 | tool schemas |
| GET    | `/api/events/recent`   | `?n=50`                           | recent bus events |

### 4.2 WebSocket

| Path         | Direction      | Frames |
|--------------|----------------|--------|
| `/ws/chat`   | bidirectional  | client → `{"text": "..."}`, server → `{"type": "text"\|"tool"\|"usage"\|"done"\|"error", "data": {...}}` |
| `/ws/events` | server → client | `{"type": "event", "data": {topic, source, ts, payload}}` — every internal event |

### 4.3 Schemas (excerpt)

```python
class CommandRequest(BaseModel):
    text: str
    conversation_id: str | None = None
    stream: bool = False

class CommandResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallTrace] = []
    usage: dict[str, int]
    iterations: int
```

See `backend/api/schemas.py` for the full set.

---

## 5. Database schema

| Table            | Purpose |
|------------------|---------|
| `conversations`  | One row per chat thread. |
| `messages`       | All turns; FK to conversation. |
| `tool_executions`| Audit log: `tool_name`, `input`, `output`, `ok`, `duration_ms`. |
| `memory_items`   | Episodic + semantic memories with `kind`, `meta`. |
| `user_patterns`  | Learned heuristics ("opens VSCode every morning at 9"). |
| `workflows`      | Persisted workflow definitions. |
| `workflow_runs`  | Execution history with outcomes JSON. |

ChromaDB stores embeddings of `memory_items` whose `kind ∈ {fact, preference, observation}`
and meaningful actions. Same `id` is used in SQL and Chroma so you can join.

---

## 6. Integration with Claude

### 6.1 Function calling pattern

```python
response = client.messages.create(
    model="claude-sonnet-4-5",
    system=[                         # ← list, so we can mark blocks cacheable
        {"type": "text", "text": SYSTEM_PROMPT,
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": context.serialize_for_llm()},
    ],
    tools=registry.schema_for_anthropic(),
    messages=memory.working_memory(),
)

if response.stop_reason == "tool_use":
    # run each tool, append tool_result blocks, call again
    ...
```

### 6.2 Token & cost management (`backend/utils/token_meter.py`)

- Every turn calls `TokenMeter.add(model, input_tokens, output_tokens)`.
- Cost is computed from `PRICE_TABLE` (update with current Anthropic prices).
- Surface the running total in `/api/health` once you wire it in.

### 6.3 Caching strategy

- **Prompt cache (90% input cost off after first hit):** the static
  `SYSTEM_PROMPT` and `tools` schema sit in cacheable blocks. Both are stable
  across requests.
- **Vector recall as a cache substitute:** instead of stuffing all history
  into context, we semantic-recall the top-k relevant memories per request.
- **Model tiering:** quick tasks (intent classification, summarizing screen)
  go to `SCAWWARD_FAST_MODEL` (Haiku); heavy reasoning goes to Sonnet.

---

## 7. Security & privacy

**Do**

- Keep `ANTHROPIC_API_KEY` in `.env`, never in code, never in git.
- Set `SCAWWARD_ALLOWED_PATHS` explicitly. Empty means "sandbox only".
- Always set `SCAWWARD_BLOCKED_PATHS` to include `C:\Windows`, `C:\Program Files`,
  `~/.ssh`, `~/.aws`, etc.
- Keep `SCAWWARD_REQUIRE_CONFIRMATION=true` for any deploy you didn't write.
- Run Scawward as a **non-admin user** so the OS is your last line of defense.

**Don't**

- Don't expose the FastAPI port outside `127.0.0.1`. There's no auth (yet).
- Don't trust the LLM with credentials. Tools that need secrets read them
  from env, not from the agent's input.
- Don't disable the policy engine "just for testing". Add a new rule instead.
- Don't let the agent run shell commands containing user-supplied template
  variables without escaping. The current shell tool refuses dangerous
  patterns; add allowlist mode if you build a public-facing UI.

**Future:** end-to-end encrypted memory with a user-supplied passphrase, plus
a per-tool capability token model so individual workflows can run with reduced
privileges.

---

## 8. Testing strategy

| Layer | Approach |
|---|---|
| Pure functions (policy, registry, workflow templating) | Unit tests, sync. |
| Async I/O (event bus, memory) | `pytest-asyncio`. |
| Tool calls | Stub `SystemExecutor` (`tests/conftest.py::fake_executor`). |
| Agentic loop | Replay-based: record an `(input, tool_calls, output)` trace; assert tool sequence and final-text invariants. |
| Vision / browser | Smoke tests behind `@pytest.mark.slow`, run in CI nightly. |

**Success metrics for an autonomous system**

- **Task success rate**: % of user requests that complete without manual
  correction, by category (file, browser, system, multi-step).
- **Tool selection accuracy**: did the agent pick the right tool first try?
- **Iteration efficiency**: average tool calls per task. Bigger ≠ better.
- **Cost per task**: USD per successful task, by model.
- **Recovery rate**: of failed tool calls, how many led to a successful retry?
- **Latency p50 / p95**: time from user input to final token.
- **Safety incidents**: any policy denial, any unintended write outside
  `ALLOWED_PATHS`. Should be zero.

Track these in a `metrics` table you can populate from `tool_executions`
+ `messages` later.

---

## 9. Three biggest technical challenges (and how this design handles them)

### 9.1 Latency on multi-step tasks

A 5-step plan can mean 5 round trips to Claude → 8-15 seconds.
**Mitigations:** (a) prompt cache on `SYSTEM_PROMPT` + tools; (b) streaming
to the UI so the user sees progress immediately; (c) parallel tool execution
where the agent returns multiple `tool_use` blocks (the current code runs
them sequentially for determinism — easy to flip via `asyncio.gather`).

### 9.2 Hallucinated tool calls

The model occasionally invents a tool name or wrong arg shape.
**Mitigations:** (a) strict JSON-schema validation in `ToolRegistry.execute`
returns a structured error the agent reads and recovers from; (b) `MAX_TOOL_ITERATIONS`
prevents loops; (c) we log every failure as an episodic memory so the agent
can avoid the same mistake next time (via semantic recall).

### 9.3 Trust boundary on a real PC

The whole point is to do *real* things, but a single bad shell command
is catastrophic.
**Mitigations:** (a) two-tier path policy (`allowed` for writes, `blocked`
for everything); (b) regex-blocked dangerous shell patterns; (c)
`requires_confirmation` on delete/overwrite/network-shell; (d) every action
logged to `tool_executions`; (e) tools never get raw shell unless the user
explicitly enables it.

---

## 10. Five "wow" features for later

1. **Screen → action loop**: vision watches the screen; when an error dialog
   appears in any app, Scawward reads it and offers a one-click fix.
2. **"Just do this for me"**: drag a PDF onto the chat → "extract invoices,
   fill spreadsheet, email accountant" runs as one workflow.
3. **Voice + interrupt**: full-duplex voice with barge-in, so you can correct
   mid-action. Pairs perfectly with Phase 2 holographic UI.
4. **Inter-agent delegation**: spawn a sub-agent per concurrent task with a
   restricted tool set; main agent reasons, sub-agents grind.
5. **Persistent "you"**: long-term semantic memory across years; Scawward
   remembers your projects, deadlines, vocabulary, preferred apps, and
   adapts every system prompt accordingly.

---

## 11. Killer apps (where this could really matter)

- **Power user / dev productivity**: replaces a constellation of scripts,
  shortcuts, and copy-paste between apps with one English-speaking interface.
- **Accessibility**: gives motor-impaired users a single channel to drive
  the whole computer.
- **Operations & on-call**: an in-shell investigator that reads logs,
  cross-references runbooks, and proposes (or executes) remediations.
- **Knowledge work**: the holy grail — "do my taxes," "prepare the deck,"
  "book the trip" — where the OS becomes the UI for every SaaS.
- **Education / pair programming**: a student pairs with Scawward on real
  projects; Scawward narrates what it's doing and why.

The killer app for *Phase 1* is probably **the dev workstation copilot**:
it's the audience who'll forgive rough edges and immediately feel the
productivity delta.
