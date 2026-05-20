from __future__ import annotations

from vidbyte.harnesses.time import MinimumTimeHarness


class HarnessClient:
    """Namespace client for harness operations."""

    @property
    def minimum_time(self) -> type[MinimumTimeHarness]:
        """Return the minimum-time harness class for direct subclassing."""

        return MinimumTimeHarness
