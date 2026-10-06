"""FILE: vidbyte/context/primitives/reasoning_traces.py

PURPOSE:
    Defines the immutable context-window record written by the SDK's 182
    reasoning-trace built-in tools. This file owns public, model-visible
    observability data and deterministic bounded rendering; it does not execute
    reasoning methods, judge truth, or resolve model-authored uncertainty.
ROLE IN CODEBASE:
    Imported by vidbyte.tools.builtins.reasoning and re-exported by
    vidbyte.context.primitives. ContextManager stores instances by primitive_id
    and uses to_context_text() when building the next model context.
ARCHITECTURE NOTE:
    The frozen slotted dataclass follows the existing context primitive pattern.
    Strategy execution and validation remain in the built-in tool module, while
    placement, replacement, and freezing remain ContextManager responsibilities.
FUNCTION INVENTORY:
    ReasoningTraceContextItem.to_context_text() -> str: renders one bounded
    public reasoning trace in deterministic schema order. It raises no custom
    errors and is covered by the existing SDK source/package smoke gates.
COMMON MODIFICATION PATTERNS:
    Add a field before the shared metadata tail, render it in schema order, and
    update this module plus the design doc in the same change. Preserve
    the 4,000-character bound and keep truth evaluation outside this module.
WHAT NOT TO DO IN THIS FILE:
    1. Do not validate tool calls; vidbyte/tools/builtins/reasoning/_base.py owns that.
    2. Do not choose context placement; vidbyte/context/manager.py owns placement.
    3. Do not add hidden chain-of-thought storage or network reporting here.
KNOWN EDGE CASES:
    Long field values are retained in the dataclass but shortened only in the
    rendered text. Confidence is expected to be validated by the tool, while a
    directly constructed primitive preserves the caller's supplied value.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/reasoning-deep-observability-tools.md
TESTS:
    Existing source compilation, context write-path, and package smoke gates in
    scripts/run_ci.py cover importability and rendering integration; no new
    feature test file is added by this no-tests design.
CONCURRENCY MODEL:
    The primitive is immutable after construction. Concurrent replacement and
    registry access are governed by the caller's ContextManager lifecycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from vidbyte.context.primitives.base import _truncate_text


@dataclass(frozen=True, slots=True)
class ReasoningTraceContextItem:
    """Store one strategy-specific public reasoning checkpoint for later turns."""

    primitive_id: str
    strategy_name: str
    strategy_purpose: str
    question: str = ""
    strategy_application: str = ""
    evidence: str = ""
    assumptions: str = ""
    alternatives: str = ""
    disconfirming_signals: str = ""
    confidence: float | None = None
    next_action: str = ""
    title: str = "Reasoning Trace"
    max_chars: int = 4000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "reasoning_trace"
    primitive_frozen: bool = False
    strategy_fields: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy_fields", MappingProxyType(dict(self.strategy_fields)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_context_text(self) -> str:
        # Renders strategy-owned fields in declaration order under one context bound.
        lines = [
            "This primitive carries a strategy-specific reasoning checkpoint for later model iterations. The strategy name and purpose identify the reasoning method, while the following fields record its question, application, evidence, assumptions, alternatives, signals, confidence, and next action. Some records use dynamic strategy-owned fields instead of the fallback field set, and both forms remain descriptive observations. Use this trace to inspect reasoning state without treating it as verified truth or executable strategy logic.",
            "",
            f"Strategy: {self.strategy_name}",
            f"Strategy Purpose: {self.strategy_purpose}",
        ]
        if self.strategy_fields:
            lines.extend(
                f"{name.replace('_', ' ').title()}: {self._render_value(value)}"
                for name, value in self.strategy_fields.items()
            )
        else:
            lines.extend(
                (
                    f"Question: {self.question}",
                    f"Strategy Application: {self.strategy_application}",
                    f"Evidence: {self.evidence}",
                    f"Assumptions: {self.assumptions}",
                    f"Alternatives: {self.alternatives}",
                    f"Disconfirming Signals: {self.disconfirming_signals}",
                    f"Confidence: {self.confidence:.2f}" if self.confidence is not None else "Confidence: N/A",
                    f"Next Action: {self.next_action}",
                )
            )
        return _truncate_text("\n".join(lines), self.max_chars)

    @staticmethod
    def _render_value(value: Any) -> str:
        if isinstance(value, (tuple, list)):
            return "; ".join(str(item) for item in value)
        return str(value)


__all__ = ["ReasoningTraceContextItem"]
