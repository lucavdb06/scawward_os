"""
PolicyEngine — single source of truth for "is this action allowed?".

Three-tier model:
  ALLOW          → execute silently
  CONFIRM        → execute but flag for UI confirmation
  DENY           → refuse with reason

Rules are declarative so they're easy to audit. Add rules in `_default_rules`
or load from YAML later.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    allowed: bool
    requires_confirmation: bool = False
    reason: str = ""


@dataclass
class Rule:
    name: str
    matches: Callable[[str, dict[str, Any]], bool]
    decision: Callable[[str, dict[str, Any]], Decision]


# ─── Pattern helpers ─────────────────────────────────────────────────
_DANGEROUS_SHELL = re.compile(
    r"(\brm\s+-rf\b|\bformat\s+[a-z]:|del\s+/[fsq]|shutdown|reg\s+delete|"
    r"diskpart|mkfs|dd\s+if=|>\s*/dev/sd[a-z])",
    re.IGNORECASE,
)

_NETWORK_HEAVY = re.compile(r"(curl|wget|invoke-webrequest|powershell.+downloadstring)",
                            re.IGNORECASE)


class PolicyEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.cfg = settings or get_settings()
        self.rules: list[Rule] = list(self._default_rules())

    async def evaluate(self, tool: str, input_: dict[str, Any]) -> Decision:
        for rule in self.rules:
            try:
                if rule.matches(tool, input_):
                    d = rule.decision(tool, input_)
                    logger.debug("policy %s → %s", rule.name, d)
                    return d
            except Exception:
                logger.exception("policy rule %s blew up", rule.name)
        return Decision(allowed=True)

    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)

    # ─── Default rules ────────────────────────────────────────────
    def _default_rules(self) -> list[Rule]:
        confirm = self.cfg.require_confirmation

        def deny_dangerous_shell() -> Rule:
            def m(tool: str, i: dict[str, Any]) -> bool:
                return tool == "shell" and bool(_DANGEROUS_SHELL.search(i.get("command", "")))
            def d(_t: str, _i: dict[str, Any]) -> Decision:
                return Decision(False, reason="destructive shell command")
            return Rule("deny.dangerous_shell", m, d)

        def confirm_delete() -> Rule:
            def m(tool: str, _i: dict[str, Any]) -> bool:
                return tool == "delete_file" and confirm
            def d(_t: str, _i: dict[str, Any]) -> Decision:
                return Decision(True, requires_confirmation=True,
                                reason="delete requires user OK")
            return Rule("confirm.delete", m, d)

        def confirm_overwrite() -> Rule:
            def m(tool: str, i: dict[str, Any]) -> bool:
                return tool == "write_file" and i.get("overwrite") and confirm
            def d(_t: str, _i: dict[str, Any]) -> Decision:
                return Decision(True, requires_confirmation=True,
                                reason="overwrite requires user OK")
            return Rule("confirm.overwrite", m, d)

        def confirm_shell_network() -> Rule:
            def m(tool: str, i: dict[str, Any]) -> bool:
                return tool == "shell" and bool(_NETWORK_HEAVY.search(i.get("command", ""))) and confirm
            def d(_t: str, _i: dict[str, Any]) -> Decision:
                return Decision(True, requires_confirmation=True,
                                reason="network access from shell")
            return Rule("confirm.shell_network", m, d)

        return [
            deny_dangerous_shell(),
            confirm_delete(),
            confirm_overwrite(),
            confirm_shell_network(),
        ]
