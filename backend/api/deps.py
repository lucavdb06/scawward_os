"""
FastAPI dependency-injection wiring.

Builds and caches the singleton "app stack":
  EventBus → Policy → Executor → Tools → Vector → Episodic →
  Memory → Context → Agent → CommandProcessor
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from ..config import Settings, get_settings
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


def _runtime_llm_path(cfg: Settings) -> Path:
    return Path(cfg.data_dir) / "runtime_llm.json"


class AppStack:
    """Holds every long-lived singleton and exposes them by name."""

    def __init__(self) -> None:
        cfg = get_settings()
        self.bus = get_bus()
        self.policy = PolicyEngine()
        self.executor = SystemExecutor(self.policy)
        self.vector = ChromaVectorStore()
        self.episodic = SqlEpisodicStore()
        self.memory = MemoryEngine(self.vector, self.episodic)
        self.tools: ToolRegistry = build_default_registry(self.executor, self.memory)
        self.context = ContextManager(self.bus)

        self.llm_provider_name: str = (cfg.provider or "anthropic").strip().lower()
        self.llm_ollama_model: str = cfg.ollama_model

        self.provider: LLMProvider = _build_provider()
        self.agent = ScawwardAgent(
            self.tools, self.memory, self.context, self.policy,
            self.provider, self.bus,
        )
        self.commands = CommandProcessor(self.agent, self.bus)
        self.workflows = WorkflowEngine(self.agent, self.tools, self.bus)

        self._apply_runtime_file(cfg)
        self.agent.runtime_model = self.active_llm_label()

    def _apply_runtime_file(self, cfg: Settings) -> None:
        path = _runtime_llm_path(cfg)
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("invalid runtime_llm.json, ignoring")
            return
        prov = (data.get("provider") or "").strip().lower()
        if prov not in {"anthropic", "ollama"}:
            return
        om = data.get("ollama_model") or cfg.ollama_model
        try:
            self.set_llm(prov, om if prov == "ollama" else None, persist=False)
        except ValueError as e:
            logger.warning("runtime_llm restore skipped: %s", e)

    def set_llm(
        self,
        provider: str,
        ollama_model: str | None = None,
        *,
        persist: bool = True,
    ) -> None:
        """Swap the in-process LLM without restarting the server."""
        cfg = get_settings()
        p = provider.strip().lower()
        if p not in {"anthropic", "ollama"}:
            raise ValueError("provider must be 'anthropic' or 'ollama'")
        if p == "anthropic" and not (cfg.anthropic_api_key or "").strip():
            raise ValueError("ANTHROPIC_API_KEY not configured")
        if p == "ollama":
            om = (ollama_model or self.llm_ollama_model or cfg.ollama_model).strip()
            self.agent.provider = OllamaProvider(
                host=cfg.ollama_host,
                default_model=om,
                request_timeout=cfg.ollama_timeout,
            )
            self.llm_provider_name = "ollama"
            self.llm_ollama_model = om
            logger.info("switched LLM → ollama model=%s", om)
        else:
            self.agent.provider = AnthropicProvider(api_key=cfg.anthropic_api_key)
            self.llm_provider_name = "anthropic"
            logger.info("switched LLM → anthropic model=%s", cfg.model)

        self.agent.runtime_model = self.active_llm_label()

        if persist:
            path = _runtime_llm_path(cfg)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "provider": self.llm_provider_name,
                            "ollama_model": self.llm_ollama_model,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                logger.exception("failed to save runtime_llm.json")

    def active_llm_label(self) -> str:
        """Human-readable model line for /api/health."""
        cfg = get_settings()
        if self.llm_provider_name == "ollama":
            return self.llm_ollama_model
        return cfg.model


@lru_cache
def get_stack() -> AppStack:
    return AppStack()
