"""FILE: vidbyte/agents/jev/compute/budget.py

PURPOSE: Implements JevComputeBudget, the run-local limit on compute moves: how many moves a run may make, how many helper agents it may start, and how many main-loop iterations it must wait after a move before the next.
ROLE IN CODEBASE: JevComputeController asks `blocked` before every move and calls `spend` after a move starts its helpers; a blocked move is recorded with the limit that stopped it.
ARCHITECTURE NOTE: The budget is code policy over counts, never a Jev decision, and it is the single authority over how much extra compute a run can spend, so every move draws from it and none can grow a run without bound. A move is charged once its helpers start, whether they succeed or not, because their compute is spent either way.
COMMON MODIFICATION PATTERNS: Add a new limit as a JevComputeSettings field, check it in `blocked` with its own JevComputeMoveStatus, and test it.
KNOWN EDGE CASES: `max_moves=0` blocks every move, which keeps recognition running with nothing acted on. The cooldown counts from the iteration of the last move, so a run with no move yet is never cooling down.
RELATED DOCS: docs/design/jev-compute-reset.md.
TESTS: tests/test_jev_compute_reset.py.
"""

from __future__ import annotations

from vidbyte.agents.jev.settings import JevComputeSettings
from vidbyte.lib.enums.jev import JevComputeMoveStatus


class JevComputeBudget:
    """The run-local limit on compute moves: their number, the helpers they start, and the wait between them."""

    def __init__(self, compute: JevComputeSettings) -> None:
        # Keeps the configured limits and starts with nothing spent.
        self.compute = compute
        self.begin()

    def begin(self) -> None:
        """Start a new run with no moves made and no helpers started."""
        self.moves = 0
        self.helpers = 0
        self.last_move_iteration: int | None = None

    def blocked(self, iteration: int, helpers: int) -> JevComputeMoveStatus | None:
        """Return the limit that stops a move needing `helpers` helpers at this iteration, or None when the move may run."""
        # @intent every-move-draws-from-one-budget
        # Each limit is checked before any helper starts, so a recognized situation can never spend more compute
        # than the run allows, and the cooldown keeps one long stuck stretch from setting off a move at every refresh.
        if self.moves >= self.compute.max_moves:
            return JevComputeMoveStatus.MOVE_LIMIT
        if self.helpers + helpers > self.compute.max_helpers:
            return JevComputeMoveStatus.HELPER_LIMIT
        if self.last_move_iteration is not None and iteration - self.last_move_iteration < self.compute.cooldown_iterations:
            return JevComputeMoveStatus.COOLDOWN
        return None

    def spend(self, iteration: int, helpers: int) -> None:
        """Charge one move that started `helpers` helpers at this iteration."""
        self.moves += 1
        self.helpers += helpers
        self.last_move_iteration = iteration


__all__ = ["JevComputeBudget"]
