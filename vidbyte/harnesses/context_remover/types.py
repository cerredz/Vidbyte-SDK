from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.errors import HarnessConfigurationError
from vidbyte.shared import LedgerEntry


@dataclass(frozen=True, slots=True)
class PurificationContract:
    """Rules for what the purifier should preserve and remove."""

    include_core_facts: bool = True
    include_tool_values: bool = True
    include_verified_state_changes: bool = True
    exclude_failed_attempts_unless_relevant: bool = True
    max_summary_chars: int = 8000

    def __post_init__(self) -> None:
        if self.max_summary_chars <= 0:
            raise HarnessConfigurationError("max_summary_chars must be greater than zero")

    def to_instruction_text(self) -> str:
        return "\n".join(
            [
                f"Include core semantic facts: {self.include_core_facts}",
                f"Include definitive tool values used downstream: {self.include_tool_values}",
                f"Include verified state changes: {self.include_verified_state_changes}",
                f"Exclude failed attempts unless relevant: {self.exclude_failed_attempts_unless_relevant}",
                f"Maximum summary characters: {self.max_summary_chars}",
            ]
        )


@dataclass(frozen=True, slots=True)
class ContextRemoverConfig:
    """Configuration for periodic trace purification."""

    purify_every_n_steps: int = 3
    prompt_key: str = "harnesses.context_remover.purify"
    retain_last_entries: int = 0
    max_raw_ledger_chars: int = 200_000

    def __post_init__(self) -> None:
        if self.purify_every_n_steps <= 0:
            raise HarnessConfigurationError("purify_every_n_steps must be greater than zero")
        if self.retain_last_entries < 0:
            raise HarnessConfigurationError("retain_last_entries must be zero or greater")
        if self.max_raw_ledger_chars <= 0:
            raise HarnessConfigurationError("max_raw_ledger_chars must be greater than zero")


@dataclass(slots=True)
class ConditionalHarnessState:
    """Mutable context matrix wrapped by ContextRemoverHarness."""

    original_intent: str
    history: list[LedgerEntry] = field(default_factory=list)
    baseline_context: str = ""
    token_offset: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PurificationResult:
    """Result of one destructive context purification pass."""

    summary: str
    before_entries: int
    after_entries: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


__all__ = [
    "ConditionalHarnessState",
    "ContextRemoverConfig",
    "PurificationContract",
    "PurificationResult",
]
