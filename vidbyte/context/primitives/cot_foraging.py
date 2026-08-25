"""Context Protocol Header

Description:
    Defines the information-foraging monitoring primitives.
Purpose:
    Gives the cot_foraging tools typed, bounded context units tracking why a
    search was launched, what it was planned to cover, what it yielded, and
    when evidence was declared sufficient.
Architecture:
    - SearchWhyContextItem, SearchPlanContextItem, SearchYieldContextItem,
      EnoughContextItem: frozen, slotted dataclasses with deterministic
      renderers bounded by max_chars.
Relations:
    Written by vidbyte.tools.builtins.cot.foraging and re-exported through
    vidbyte.context.primitives.
Similar Files:
    - `vidbyte/context/primitives/cot_events.py`
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.context.primitives.base import _extend_section, _truncate_text

_DEFAULT_MAX_CHARS = 2000


@dataclass(frozen=True, slots=True)
class SearchWhyContextItem:
    """Records the specific missing fact that motivated a search.

    Each entry converts an impulse to search into a stated plan: the exact
    gap in knowledge, the step it blocks, the condition that ends the search,
    and — when it matters — how urgently the gap needs closing. Recording
    this before the search runs makes wandering, unbounded search visible as
    a pattern rather than an invisible cost, since a search that never had a
    stated stop condition has no honest way to declare itself finished.
    """

    missing_fact: str
    why_needed: str
    stop_condition: str
    expected_source: str | None = None
    fallback_if_not_found: str = ""
    urgency: str | None = None
    title: str = "Search Why"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "search_why"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the search motivation and its stop condition, bounded by max_chars.
        lines = [
            f"Missing Fact: {self.missing_fact}",
            f"Why Needed: {self.why_needed}",
            f"Stop Condition: {self.stop_condition}",
        ]
        if self.urgency:
            lines.append(f"Urgency: {self.urgency}")
        if self.expected_source:
            lines.append(f"Expected Source: {self.expected_source}")
        if self.fallback_if_not_found:
            lines.append(f"Fallback If Not Found: {self.fallback_if_not_found}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class SearchPlanContextItem:
    """Records the queries about to run and the rationale for their order.

    The record holds the shape of a search round before it executes: the
    individual queries with their expected yields, why they are sequenced the
    way they are, the budget of queries allowed before the agent must
    reconsider strategy, and — when applicable — whether the queries could
    run in parallel and what happens if the whole round comes up empty. A
    round with a stated plan either finds its target or fails in a way that
    is informative, rather than quietly consuming steps with no shape at all.
    """

    queries: tuple[Mapping[str, Any], ...]
    order_rationale: str
    max_queries: int | None = None
    abort_if: str | None = None
    parallelizable: str | None = None
    fallback_strategy: str | None = None
    title: str = "Search Plan"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "search_plan"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the planned queries with expected yields, bounded by max_chars.
        lines = [f"Order Rationale: {self.order_rationale}"]
        if self.max_queries is not None:
            lines.append(f"Max Queries: {self.max_queries}")
        if self.parallelizable:
            lines.append(f"Parallelizable: {self.parallelizable}")
        if self.abort_if:
            lines.append(f"Abort If: {self.abort_if}")
        if self.fallback_strategy:
            lines.append(f"Fallback Strategy: {self.fallback_strategy}")
        query_lines = tuple(
            f"{entry.get('query', '')} [{entry.get('expected_yield', 'exploratory')}] -> {entry.get('target', '')}"
            for entry in self.queries
        )
        _extend_section(lines, "Planned Queries", query_lines)
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class SearchYieldContextItem:
    """Records what a search round actually produced relative to expectations.

    This is the closing half of the search_why/search_plan pair: it reports
    the honest outcome of a completed round, including query counts that
    exceeded the planned budget, and the deliberate next move chosen in
    response. A round that contradicts the searcher's premise entirely is
    recorded here as the valuable finding it is, rather than being folded
    quietly into an ordinary miss.
    """

    found: str
    queries_spent: int
    best_result: str | None = None
    missing_still: str | None = None
    pivot: str | None = None
    surprise: str | None = None
    title: str = "Search Yield"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "search_yield"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the yield verdict and next-move, bounded by max_chars.
        lines = [
            f"Found: {self.found}",
            f"Queries Spent: {self.queries_spent}",
        ]
        if self.best_result:
            lines.append(f"Best Result: {self.best_result}")
        if self.missing_still:
            lines.append(f"Still Missing: {self.missing_still}")
        if self.pivot:
            lines.append(f"Pivot: {self.pivot}")
        if self.surprise:
            lines.append(f"Surprise: {self.surprise}")
        return _truncate_text("\n".join(lines), self.max_chars)


@dataclass(frozen=True, slots=True)
class EnoughContextItem:
    """Records the declaration that existing evidence is sufficient to act.

    Each entry is a deliberate stop rule: a statement that the evidence
    gathered so far justifies acting, backed by the strongest point in its
    favor, the weakest link it still rests on, and — when the declaration is
    reversible — what finding would change the verdict. Naming the weakest
    link is the honesty check built into this primitive, since every
    evidence base has one and pretending otherwise converts a known risk into
    a hidden one.
    """

    acting_on: str
    evidence_count: int
    would_change_mind: str
    strongest_evidence: str
    weakest_link: str
    what_would_reverse: str | None = None
    title: str = "Enough Evidence"
    max_chars: int = _DEFAULT_MAX_CHARS
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "enough"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders the sufficiency declaration with its strongest and weakest links, bounded by max_chars.
        lines = [
            f"Acting On: {self.acting_on}",
            f"Evidence Count: {self.evidence_count}",
            f"Would Change Mind: {self.would_change_mind}",
            f"Strongest Evidence: {self.strongest_evidence}",
            f"Weakest Link: {self.weakest_link}",
        ]
        if self.what_would_reverse:
            lines.append(f"What Would Reverse It: {self.what_would_reverse}")
        return _truncate_text("\n".join(lines), self.max_chars)


__all__ = [
    "EnoughContextItem",
    "SearchPlanContextItem",
    "SearchWhyContextItem",
    "SearchYieldContextItem",
]
