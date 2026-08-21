"""Context Protocol Header

Description:
    Eight ContextItem primitives that surface a verifier runtime's ledger
    state inside an agent's context window.
Purpose:
    Lets VerifierLedger publish its history, regressions, latest diagnostics,
    remaining budget, per-verifier score trend, repair scope, tamper
    baseline, and flaky-check status as addressable, replaceable primitives
    via ContextManager.upsert() — never as an ever-growing unmanaged list.
Architecture:
    - Each class carries a fixed introductory sentence baked into
      to_context_text(), framing what the block means before the data.
    - All eight take only plain stdlib field types (str, tuple, int, float)
      so this module has no dependency on vidbyte.agents — VerifierLedger
      does the flattening from its own rich objects before constructing these.
Relations:
    Constructed by vidbyte.agents.runtimes.verifier.ledger.VerifierLedger.to_context_items().
    Re-exported by vidbyte.context.primitives.
Similar Files:
    - vidbyte/context/primitives/tasks.py: ProgressContextItem, the nearest
      existing "renders a short intro plus a status list" primitive.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

_HISTORY_INTRO = (
    "The following is the history of verification attempts made so far during this run. "
    "Each entry lists the attempt number, which checks ran, and whether they passed."
)
_REGRESSION_INTRO = (
    "The following checks previously passed earlier in this run but are now failing again. "
    "This usually means a recent change reintroduced a problem that was already fixed — "
    "review it carefully before making further changes."
)
_DIAGNOSTIC_INTRO = (
    "The following is the detailed diagnostic output from the most recent failed verification "
    "attempt. Use this to understand exactly what is still wrong before trying again."
)
_BUDGET_INTRO = (
    "The following describes how much verification budget remains for this run. Once this "
    "budget is exhausted, the run will stop regardless of whether verification has passed."
)
_TREND_INTRO = (
    "The following shows how each graded verifier's score has changed across attempts in this "
    "run. A flat or worsening trend means the current approach is not converging and a "
    "different strategy may be needed."
)
_SCOPE_INTRO = (
    "The following files or symbols are the ones implicated by the most recent verification "
    "failure. Focus changes on these unless there is a clear reason to touch something else."
)
_TAMPER_INTRO = (
    "The following verification-defining files must not be modified as part of fixing a "
    "failure. Changing them instead of the underlying issue will be flagged and does not count "
    "as a genuine fix."
)
_FLAKE_INTRO = (
    "The following checks have produced inconsistent results across attempts with no "
    "corresponding change to the work — they may be flaky rather than reflecting a real "
    "problem. Treat repeated failures here with some skepticism."
)


@dataclass(slots=True)
class VerifierHistoryContextItem:
    """Publishes the run's verification attempt history."""

    entries: tuple[str, ...]
    kind: str = "verifier_history"
    title: str = "Verification History"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    primitive_id: str = "verifier:history"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Renders the fixed intro sentence followed by one line per recorded attempt."""
        lines = [_HISTORY_INTRO, ""]
        lines.extend(f"- {entry}" for entry in self.entries)
        return "\n".join(lines)


@dataclass(slots=True)
class VerifierRegressionContextItem:
    """Publishes verifiers that previously passed and are now failing again."""

    regressed_names: tuple[str, ...]
    kind: str = "verifier_regression"
    title: str = "Verification Regressions"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    primitive_id: str = "verifier:regression"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Renders the fixed intro sentence followed by the list of regressed verifier names."""
        lines = [_REGRESSION_INTRO, ""]
        lines.extend(f"- {name}" for name in self.regressed_names)
        return "\n".join(lines)


@dataclass(slots=True)
class VerifierDiagnosticContextItem:
    """Publishes the most recent attempt's failing diagnostics."""

    diagnostics: tuple[str, ...]
    kind: str = "verifier_diagnostic"
    title: str = "Latest Verification Diagnostics"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    primitive_id: str = "verifier:diagnostic"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Renders the fixed intro sentence followed by every failing verifier's diagnostic line."""
        lines = [_DIAGNOSTIC_INTRO, ""]
        lines.extend(f"- {line}" for line in self.diagnostics)
        return "\n".join(lines)


@dataclass(slots=True)
class VerifierBudgetContextItem:
    """Publishes the run's remaining verification budget."""

    remaining_attempts: int
    max_attempts: int
    kind: str = "verifier_budget"
    title: str = "Verification Budget"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    primitive_id: str = "verifier:budget"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Renders the fixed intro sentence followed by remaining and total attempt counts."""
        return f"{_BUDGET_INTRO}\n\n- Remaining attempts: {self.remaining_attempts} of {self.max_attempts}"


@dataclass(slots=True)
class VerifierTrendContextItem:
    """Publishes each graded verifier's score trend across attempts."""

    trend_lines: tuple[str, ...]
    kind: str = "verifier_trend"
    title: str = "Verification Score Trend"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    primitive_id: str = "verifier:trend"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Renders the fixed intro sentence followed by one pre-rendered trend line per verifier."""
        lines = [_TREND_INTRO, ""]
        lines.extend(f"- {line}" for line in self.trend_lines)
        return "\n".join(lines)


@dataclass(slots=True)
class VerifierScopeContextItem:
    """Publishes the edit scope implicated by the most recent verification failure."""

    scope: tuple[str, ...]
    kind: str = "verifier_scope"
    title: str = "Verification Repair Scope"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    primitive_id: str = "verifier:scope"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Renders the fixed intro sentence followed by the implicated file/symbol tokens."""
        lines = [_SCOPE_INTRO, ""]
        lines.extend(f"- {path}" for path in self.scope)
        return "\n".join(lines)


@dataclass(slots=True)
class VerifierTamperContextItem:
    """Publishes the verification-defining files that must not be edited as a shortcut."""

    protected_paths: tuple[str, ...]
    kind: str = "verifier_tamper"
    title: str = "Protected Verification Files"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    primitive_id: str = "verifier:tamper"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Renders the fixed intro sentence followed by every protected file path."""
        lines = [_TAMPER_INTRO, ""]
        lines.extend(f"- {path}" for path in self.protected_paths)
        return "\n".join(lines)


@dataclass(slots=True)
class VerifierFlakeContextItem:
    """Publishes verifiers whose results have flip-flopped without a corresponding change."""

    flaky_names: tuple[str, ...]
    kind: str = "verifier_flake"
    title: str = "Possibly Flaky Checks"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    primitive_id: str = "verifier:flake"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        """Renders the fixed intro sentence followed by the list of possibly-flaky verifier names."""
        lines = [_FLAKE_INTRO, ""]
        lines.extend(f"- {name}" for name in self.flaky_names)
        return "\n".join(lines)


__all__ = [
    "VerifierBudgetContextItem",
    "VerifierDiagnosticContextItem",
    "VerifierFlakeContextItem",
    "VerifierHistoryContextItem",
    "VerifierRegressionContextItem",
    "VerifierScopeContextItem",
    "VerifierTamperContextItem",
    "VerifierTrendContextItem",
]
