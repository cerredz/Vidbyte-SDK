from __future__ import annotations

from vidbyte.harnesses.context_remover import ContextRemoverHarness
from vidbyte.harnesses.red_team import RedTeamChallengeHarness


class HarnessClient:
    """Namespace client for harness operations."""

    @property
    def red_team_challenge(self) -> type[RedTeamChallengeHarness]:
        """Return the red-team challenge harness class."""

        return RedTeamChallengeHarness

    @property
    def context_remover(self) -> type[ContextRemoverHarness]:
        """Return the context remover harness class."""

        return ContextRemoverHarness
