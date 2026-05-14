"""Centralized settings, loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SCAWWARD_",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── LLM provider selection ───────────────────────────────────
    # "anthropic" (Claude, paid) or "ollama" (local GPU, free).
    provider: str = "anthropic"

    # ─── Anthropic (no SCAWWARD_ prefix on this one) ──────────────
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    model: str = "claude-sonnet-4-5"
    fast_model: str = "claude-haiku-4-5"
    vision_model: str = "claude-sonnet-4-5"
    max_tokens: int = 4096
    temperature: float = 0.2

    # ─── Ollama (local GPU) ───────────────────────────────────────
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.1:latest"     # used when provider=ollama
    ollama_timeout: float = 300.0

    # ─── Server ───────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"
    debug: bool = True

    # ─── Storage ──────────────────────────────────────────────────
    db_url: str = "sqlite+aiosqlite:///./data/scawward.db"
    vector_db_path: str = "./data/chroma"

    # ─── Security ─────────────────────────────────────────────────
    require_confirmation: bool = True
    sandbox_root: str = "./data/sandbox"
    allowed_paths: str = ""        # comma-separated
    blocked_paths: str = ""        # comma-separated

    # ─── Vision ───────────────────────────────────────────────────
    screenshot_interval: int = 5
    screenshot_downscale: float = 0.5

    # ─── Cache ────────────────────────────────────────────────────
    cache_ttl: int = 3600
    prompt_cache_enabled: bool = True

    # ─── Computed: pick the right model for the active provider ───
    @property
    def active_model(self) -> str:
        if (self.provider or "").strip().lower() == "ollama":
            return self.ollama_model
        return self.model

    # ─── Computed paths ───────────────────────────────────────────
    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def data_dir(self) -> Path:
        d = self.project_root / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def allowed_path_list(self) -> list[Path]:
        return [Path(p.strip()) for p in self.allowed_paths.split(",") if p.strip()]

    @property
    def blocked_path_list(self) -> list[Path]:
        return [Path(p.strip()) for p in self.blocked_paths.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
