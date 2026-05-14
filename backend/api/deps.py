"""
FastAPI dependency-injection wiring.

Builds and caches the singleton "app stack":
  EventBus → Policy → Executor → Tools → Vector → Episodic →
  Memory → Context → Agent → CommandProcessor
"""
from __future__ import annotations

from functools import lru_cache

import logging

from ..config import get_settings
from ..core.context_manager import ContextManager
from ..core.event_bus import get_bus
from ..core.llm import LLMProvider
from ..core.llm.anthropic_provider import AnthropicProvider
from ..core.llm.ollama_provider import OllamaProvider
from ..core.memory_engine import MemoryEngine
from ..core.scawward_agent import ScawwardAgent
from ..core.system_executor import SystemExecutor
from ..db.repositories import SqlEpisodicStore
from ..db.vector_store import ChromaVectorStore
from ..modules.command_processor import CommandProcessor
from ..modules.workflow_engine import WorkflowEngine
from ..security.policy import PolicyEngine
from ..tools.registry import ToolRegistry, build_default_registry

logger = logging.getLogger(__name__)


def _build_provider() -> LLMProvider:
    """Pick the LLM backend based on `SCAWWARD_PROVIDER`."""
    cfg = get_settings()
    name = (cfg.provider or "anthropic").strip().lower()
    if name == "ollama":
        logger.info("LLM provider: ollama (host=%s, model=%s)",
                    cfg.ollama_host, cfg.ollama_model)
        return OllamaProvider(
            host=cfg.ollama_host,
            default_model=cfg.ollama_model,
            request_timeout=cfg.ollama_timeout,
        )
    if name != "anthropic":
        logger.warning("unknown provider %r, falling back to anthropic", name)
    logger.info("LLM provider: anthropic (model=%s)", cfg.model)
    return AnthropicProvider(api_key=cfg.anthropic_api_key)


class AppStack:
    """Holds every long-lived singleton and exposes them by name."""

    def __init__(self) -> None:
        self.bus = get_bus()
        self.policy = PolicyEngine()
        self.executor = SystemExecutor(self.policy)
        self.vector = ChromaVectorStore()
        self.episodic = SqlEpisodicStore()
        self.memory = MemoryEngine(self.vector, self.episodic)
        self.tools: ToolRegistry = build_default_registry(self.executor, self.memory)
        self.context = ContextManager(self.bus)
        self.provider: LLMProvider = _build_provider()
        self.agent = ScawwardAgent(
            self.tools, self.memory, self.context, self.policy,
            self.provider, self.bus,
        )
        self.commands = CommandProcessor(self.agent, self.bus)
        self.workflows = WorkflowEngine(self.agent, self.tools, self.bus)


@lru_cache
def get_stack() -> AppStack:
    return AppStack()
