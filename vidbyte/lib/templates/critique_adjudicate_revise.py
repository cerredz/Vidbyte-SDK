"""Context Protocol Header

FILE: vidbyte/lib/templates/critique_adjudicate_revise.py
PURPOSE: Defines the successful recorder-slot contract for one critique-adjudicate-
    revise run. It validates structure only and never contains review content.
ROLE IN CODEBASE: Exported by vidbyte/lib/templates/__init__.py and used with recorder
    events emitted by CritiqueAdjudicateReviseRuntimeAlgorithm.
ARCHITECTURE NOTE: Critic completion is concurrent, so one fan-out slot and one full-
    barrier slot are deterministic; per-critic completion belongs in tracing/metadata.
FUNCTION INVENTORY: CritiqueAdjudicateReviseContextWindowTemplate constructs either
    the revised or valid revision-skipped successful sequence.
COMMON MODIFICATION PATTERNS: Change slots only with adapter instrumentation and the
    context-window template skill documentation.
WHAT NOT TO DO IN THIS FILE: 1. Do not model completion order. 2. Do not add payloads.
KNOWN EDGE CASES: revision_expected=False means zero accepted findings, not failure.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/context-window-critique-adjudicate-revise.md
TESTS: Existing context-window template regressions; no new tests in this workflow.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate


class CritiqueAdjudicateReviseContextWindowTemplate(ContextWindowTemplate):
    """Canonical successful slot sequence for critique-adjudicate-revise."""

    def __init__(self, *, revision_expected: bool = True) -> None:
        # Selects the revised or no-accepted-findings terminal slot deterministically.
        terminal = "critique_adjudicate_revise_revision" if revision_expected else "critique_adjudicate_revise_revision_skipped"
        super().__init__(["system_prompt", "critique_adjudicate_revise_producer", "critique_adjudicate_revise_critic_fanout", "critique_adjudicate_revise_critic_barrier", "critique_adjudicate_revise_adjudication", terminal])


__all__ = ["CritiqueAdjudicateReviseContextWindowTemplate"]
