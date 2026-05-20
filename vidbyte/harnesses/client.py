# -*- coding: utf-8 -*-
#
# Context Protocol Header:
# - DESCRIPTION: Namespace client for harness operations.
# - PURPOSE: Provides a developer-facing registry and access interface for all supported harnesses.
# - ARCHITECTURE: Exposes individual harness types and classes as clean properties or instantiations.
# - KEY FUNCTIONS:
#   - HarnessClient.base(): Instantiates the BaseHarness.
#   - HarnessClient.minimum_time: Returns the MinimumTimeHarness class type.
# - RELATION TO CODEBASE: Wireup client that sits on VidbyteSDK.harnesses. Exposes new and existing evaluation and timing harnesses.
# - SIMILAR FILES: vidbyte/tools/client.py, vidbyte/strategies/client.py

from __future__ import annotations

from vidbyte.harnesses.base import BaseHarness
from vidbyte.harnesses.time.minimum_time import MinimumTimeHarness


class HarnessClient:
    """Namespace client for harness operations."""

    def base(self) -> BaseHarness:
        return BaseHarness()

    @property
    def minimum_time(self) -> type[MinimumTimeHarness]:
        """Return the minimum-time harness class for direct subclassing."""
        return MinimumTimeHarness

