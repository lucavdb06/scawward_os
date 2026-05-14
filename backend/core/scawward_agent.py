"""
ScawwardAgent — the reasoning brain.

Wraps the Anthropic API in an agentic loop:

    user → [agent] → tool_use → [executor] → tool_result → [agent] → final

Highlights
----------
* Streaming output via async generator (for WebSocket → UI).
* Multi-turn tool use with safe iteration cap.
* Prompt caching for the static system prompt + tool defs (huge cost win).
* Pluggable Tool registry (see backend/tools/registry.py).
* Confirms risky tools via the policy layer before execution.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

from ..config import Settings, get_settings
from ..security.policy import PolicyEngine
from ..tools.registry import ToolRegistry, ToolResult
from .context_manager import ContextManager
from .event_bus import EventBus, get_bus
from .llm import LLMProvider, ProviderResponse
from .memory_engine import MemoryEngine

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 8


SYSTEM_PROMPT = """\
You are SCAWWARD, an AI operating layer that pilots a real personal computer
to accomplish what the user asks.

PRINCIPLES
1. Be decisive. Pick one good plan, execute it, course-correct on errors.
2. Prefer the smallest tool sequence that achieves the goal.
3. Always tell the user what you're about to do *before* destructive
   actions (delete, overwrite, send, pay).
4. When uncertain about user intent, ask ONE crisp question — not a list.
5. Use the current_context block to ground every decision.
6. After completing a multi-step task, summarize what you did in 1-3 lines.

TOOLS
You have access to system tools (file ops, app launch, browser, shell).
Each tool has clear permissions. If a tool returns an error, read it,
adapt, and retry differently — don't repeat the same call.

OUTPUT
Respond in the user's language. Be concise. Show your work only when it
helps the user trust or verify the result.
"""


@dataclass
class AgentTurn:
    """One full request/response cycle."""
    user_input: str
    final_text: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, int]
    iterations: int


class ScawwardAgent:
    def __init__(
        self,
        tools: ToolRegistry,
        memory: MemoryEngine,
        context: ContextManager,
        policy: PolicyEngine,
        provider: LLMProvider,
        bus: EventBus | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.cfg = settings or get_settings()
        self.provider = provider
        self.tools = tools
        self.memory = memory
        self.context = context
        self.policy = policy
        self.bus = bus or get_bus()

    # ─── Public API ───────────────────────────────────────────────
    async def chat(self, user_input: str) -> AgentTurn:
        """Non-streaming convenience method."""
        chunks: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        usage = {"input": 0, "output": 0}
        iterations = 0
        async for ev in self.stream(user_input):
            kind = ev["type"]
            if kind == "text":
                chunks.append(ev["text"])
            elif kind == "tool":
                tool_calls.append(ev)
            elif kind == "usage":
                usage["input"] += ev.get("input", 0)
                usage["output"] += ev.get("output", 0)
                iterations = ev.get("iteration", iterations)
        return AgentTurn(
            user_input=user_input,
            final_text="".join(chunks),
            tool_calls=tool_calls,
            usage=usage,
            iterations=iterations,
        )

    async def stream(self, user_input: str) -> AsyncIterator[dict[str, Any]]:
        """Async generator yielding tokens / tool events.

        Event shapes:
          {"type": "text",  "text": "..."}
          {"type": "tool",  "name": "...", "input": {...}, "result": {...}}
          {"type": "usage", "input": int, "output": int, "iteration": int}
          {"type": "done"}
        """
        await self.bus.emit("user.message", {"text": user_input}, source="agent")
        self.memory.append_turn("user", user_input)

        # Pull semantically related memories from prior sessions. Failure
        # here must never break the turn — recall is best-effort context.
        try:
            recalled = await self.memory.recall(user_input, k=5)
        except Exception:
            logger.exception("memory recall failed; continuing without")
            recalled = []

        # Inject working memory + current context as a Claude-style chat history.
        messages = self._build_messages(user_input)
        sys_blocks = self._build_system_blocks(recalled)
        tools_schema = self.tools.schema_for_anthropic()

        for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
            response: ProviderResponse = await self.provider.create(
                model=self.cfg.active_model,
                max_tokens=self.cfg.max_tokens,
                temperature=self.cfg.temperature,
                system=sys_blocks,
                tools=tools_schema,
                messages=messages,
            )

            yield {
                "type": "usage",
                "input": getattr(response.usage, "input_tokens", 0),
                "output": getattr(response.usage, "output_tokens", 0),
                "iteration": iteration,
            }

            assistant_blocks: list[dict[str, Any]] = []
            tool_uses: list[dict[str, Any]] = []

            for block in response.content:
                if block.type == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                    if block.text:
                        yield {"type": "text", "text": block.text}
                elif block.type == "tool_use":
                    payload = {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                    assistant_blocks.append(payload)
                    tool_uses.append(payload)

            messages.append({"role": "assistant", "content": assistant_blocks})

            if response.stop_reason != "tool_use" or not tool_uses:
                self.memory.append_turn("assistant", assistant_blocks)
                yield {"type": "done"}
                return

            # Run all requested tools (sequentially for determinism).
            tool_results = []
            for use in tool_uses:
                result = await self._run_tool(use["name"], use["input"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": use["id"],
                    "content": json.dumps(result.to_dict()),
                    "is_error": not result.ok,
                })
                yield {
                    "type": "tool",
                    "name": use["name"],
                    "input": use["input"],
                    "result": result.to_dict(),
                }

            messages.append({"role": "user", "content": tool_results})

        logger.warning("agent hit MAX_TOOL_ITERATIONS")
        yield {"type": "text", "text": "\n[Stopped: too many tool iterations.]"}
        yield {"type": "done"}

    # ─── Internals ────────────────────────────────────────────────
    def _build_messages(self, user_input: str) -> list[dict[str, Any]]:
        # Working memory already includes the freshly appended user turn
        # via `append_turn` above.
        return list(self.memory.working_memory())

    def _build_system_blocks(
        self,
        recalled: "list[Any] | None" = None,
    ) -> list[dict[str, Any]]:
        """System prompt with prompt caching on the static portion.

        Layout:
          [0] SYSTEM_PROMPT          ← cached (ephemeral)
          [1] current context        ← refreshed every turn
          [2] recalled memories      ← optional, added only if non-empty
        """
        ctx = self.context.serialize_for_llm()
        blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"} if self.cfg.prompt_cache_enabled else None,
            },
            {"type": "text", "text": ctx},
        ]

        mem_block = self._format_recalled(recalled or [])
        if mem_block:
            blocks.append({"type": "text", "text": mem_block})

        # Anthropic SDK rejects cache_control: None — strip it.
        for b in blocks:
            if b.get("cache_control") is None:
                b.pop("cache_control", None)
        return blocks

    @staticmethod
    def _format_recalled(items: "list[Any]") -> str:
        """Render recalled memories as a compact <memories> block.

        Caps content length and item count to keep token bloat in check.
        Returns "" when there is nothing worth showing.
        """
        if not items:
            return ""
        # Surface higher-signal kinds first; bury raw action logs at the end.
        order = {"preference": 0, "fact": 1, "observation": 2, "action": 3}
        sorted_items = sorted(items, key=lambda m: order.get(m.kind, 9))[:5]

        lines = [
            "<long_term_memory>",
            "Relevant entries from past sessions. Use them as background "
            "context; do NOT echo them back at the user verbatim.",
        ]
        for m in sorted_items:
            content = (m.content or "").strip().replace("\n", " ")
            if len(content) > 200:
                content = content[:197] + "..."
            lines.append(f"  - [{m.kind}] {content}")
        lines.append("</long_term_memory>")
        return "\n".join(lines)

    async def _run_tool(self, name: str, input_: dict[str, Any]) -> ToolResult:
        await self.bus.emit("agent.tool.requested",
                            {"tool": name, "input": input_}, source="agent")

        decision = await self.policy.evaluate(name, input_)
        if not decision.allowed:
            return ToolResult.fail(f"blocked by policy: {decision.reason}")
        if decision.requires_confirmation:
            # In Phase 1 we just log; Phase 2 will round-trip through UI.
            logger.warning("tool %s requires confirmation (auto-approved in dev)", name)

        try:
            result = await self.tools.execute(name, input_)
        except Exception as e:
            logger.exception("tool %s crashed", name)
            result = ToolResult.fail(f"crash: {e!r}")

        await self.bus.emit(
            "executor.action.done",
            {"tool": name, "ok": result.ok, "summary": result.summary[:200]},
            source="agent",
        )
        # Persist a compact memory of what happened.
        await self.memory.remember(
            "action",
            f"{name}({json.dumps(input_, default=str)[:200]}) → {result.summary[:300]}",
            metadata={"tool": name, "ok": result.ok},
        )
        return result
