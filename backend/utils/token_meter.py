"""
TokenMeter — running total of tokens / estimated cost.

Anthropic charges per million tokens. This helper:
  * accumulates input/output token counts across all turns;
  * computes USD cost from a configurable price table;
  * exposes a simple `report()` for status pages.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# USD per 1M tokens (illustrative; update to current pricing).
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5":  (0.25,  1.25),
}


@dataclass
class TokenMeter:
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, model: str, input_tokens: int, output_tokens: int) -> None:
        bucket = self.by_model.setdefault(model, {"in": 0, "out": 0})
        bucket["in"] += input_tokens
        bucket["out"] += output_tokens

    def cost_usd(self) -> float:
        total = 0.0
        for model, b in self.by_model.items():
            in_p, out_p = PRICE_TABLE.get(model, (0.0, 0.0))
            total += b["in"] / 1_000_000 * in_p
            total += b["out"] / 1_000_000 * out_p
        return round(total, 4)

    def report(self) -> dict:
        return {"by_model": self.by_model, "estimated_usd": self.cost_usd()}
