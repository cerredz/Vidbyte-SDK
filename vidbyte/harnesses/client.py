from __future__ import annotations

from vidbyte.harnesses.base import BaseHarness


class HarnessClient:
    """Namespace client for harness operations."""

    def base(self) -> BaseHarness:
        return BaseHarness()
