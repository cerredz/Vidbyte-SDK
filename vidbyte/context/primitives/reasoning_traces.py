"""FILE: vidbyte/context/primitives/reasoning_traces.py

PURPOSE:
    Defines the immutable context-window record written by the SDK's 182
    reasoning-trace built-in tools. This file owns public, model-visible
    observability data and deterministic bounded rendering; it does not execute
    reasoning methods, judge truth, or resolve model-authored uncertainty.
ROLE IN CODEBASE:
    Imported by vidbyte.tools.builtins.reasoning_traces and re-exported by
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
    update reasoning_traces.py plus the design doc in the same change. Preserve
    the 4,000-character bound and keep truth evaluation outside this module.
WHAT NOT TO DO IN THIS FILE:
    1. Do not validate tool calls; vidbyte/tools/builtins/reasoning_traces.py owns that.
    2. Do not choose context placement; vidbyte/context/manager.py owns placement.
    3. Do not add hidden chain-of-thought storage or network reporting here.
KNOWN EDGE CASES:
    Long field values are retained in the dataclass but shortened only in the
    rendered text. Confidence is expected to be validated by the tool, while a
    directly constructed primitive preserves the caller's supplied value.
RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/reasoning-deep-observability-tools.md
TEST FILES:
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
from typing import Any

from vidbyte.context.primitives.base import _truncate_text


@dataclass(frozen=True, slots=True)
class ReasoningTraceContextItem:
    """Store one strategy-specific public reasoning checkpoint for later turns."""

    primitive_id: str
    strategy_name: str
    strategy_purpose: str
    question: str
    strategy_application: str
    evidence: str
    assumptions: str
    alternatives: str
    disconfirming_signals: str
    confidence: float
    next_action: str
    title: str = "Reasoning Trace"
    max_chars: int = 4000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "reasoning_trace"
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders every public trace field in schema order under one context bound.
        lines = [
            f"Strategy: {self.strategy_name}",
            f"Strategy Purpose: {self.strategy_purpose}",
            f"Question: {self.question}",
            f"Strategy Application: {self.strategy_application}",
            f"Evidence: {self.evidence}",
            f"Assumptions: {self.assumptions}",
            f"Alternatives: {self.alternatives}",
            f"Disconfirming Signals: {self.disconfirming_signals}",
            f"Confidence: {self.confidence:.2f}",
            f"Next Action: {self.next_action}",
        ]
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = ["ReasoningTraceContextItem"]
