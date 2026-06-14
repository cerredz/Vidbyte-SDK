"""Context Protocol Header

Description:
    Defines the client namespace interface for custom harnesses in the Vidbyte SDK.
Purpose:
    Exposes constructor methods to build specialized harnesses like the CompetitorGrowthHarness.
Architecture:
    - HarnessClient: Public-facing client class with helper functions.
Relation to codebase as a whole:
    Allows user access to harnesses through VidbyteSDK().harnesses.
Similar files:
    - vidbyte/client.py: Unifies all namespace clients under VidbyteSDK.
"""

from __future__ import annotations

from typing import Any
from vidbyte.harnesses.competitor_growth import CompetitorGrowthHarness


class HarnessClient:
    """Namespace client for custom harness integrations."""

    def competitor_growth(self, **kwargs: Any) -> CompetitorGrowthHarness:
        # Construct and return an instance of CompetitorGrowthHarness.
        return CompetitorGrowthHarness(**kwargs)

