"""Context Protocol Header

FILE: vidbyte/lib/templates/pairwise_tournament.py
PURPOSE: Defines the deterministic recorder-slot contract for completed pairwise
    tournaments without encoding candidate or judge content.
ROLE IN CODEBASE: Test harnesses and manual verification compare a runtime recorder
    against this ContextWindowTemplate subclass.
ARCHITECTURE NOTE: Slot shape depends only on candidate and round counts; individual
    matches and legs are represented in metadata and traces, not recorder slots.
FUNCTION INVENTORY: PairwiseTournamentContextWindowTemplate validates counts and builds
    the exact coordinator-level slot sequence.
COMMON MODIFICATION PATTERNS: Change slot emission in the runtime and this template in
    the same approved design change.
WHAT NOT TO DO: Do not add per-leg content or completion-order-dependent slots.
KNOWN EDGE CASES: Non-power-of-two candidate counts still require ceil(log2(N)) rounds.
RELATED DOCS: docs/design/context-window-pairwise-tournament.md and
    skills/vidbyte-sdk/context-window-templates.md.
TESTS: Existing template infrastructure plus manual recorder verification.
"""

from __future__ import annotations

from vidbyte.lib.templates.base import ContextWindowTemplate


class PairwiseTournamentContextWindowTemplate(ContextWindowTemplate):
    """Expected coordinator slots for one successfully completed tournament."""

    def __init__(self, *, candidate_count: int, round_count: int) -> None:
        # Validates bracket dimensions and initializes the deterministic slot sequence.
        if isinstance(candidate_count, bool) or not 2 <= candidate_count <= 16:
            raise ValueError("candidate_count must be an integer between 2 and 16.")
        expected_rounds = (candidate_count - 1).bit_length()
        if isinstance(round_count, bool) or round_count != expected_rounds:
            raise ValueError(f"round_count must be {expected_rounds} for {candidate_count} candidates.")
        super().__init__(self._build_slots(round_count))

    @staticmethod
    def _build_slots(round_count: int) -> list[str]:
        # Builds the candidate barrier, completed-round slots, and final winner slot.
        return [
            "system_prompt",
            "pairwise_tournament_candidate_fanout",
            "pairwise_tournament_candidate_barrier",
            *("pairwise_tournament_round" for _ in range(round_count)),
            "pairwise_tournament_winner",
        ]


__all__ = ["PairwiseTournamentContextWindowTemplate"]
