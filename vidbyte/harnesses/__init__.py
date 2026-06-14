"""Context Protocol Header

Description:
    Exposes the public interfaces and constructors for Vidbyte custom harnesses.
Purpose:
    Enables package-level imports of HarnessClient, CompetitorGrowthHarness, and CompetitorGrowthAnalysis.
Architecture:
    - Re-exports HarnessClient, CompetitorGrowthHarness, and CompetitorGrowthAnalysis.
Relation to codebase as a whole:
    Provides public imports for Vidbyte custom harnesses.
Similar files:
    - vidbyte/agents/__init__.py: Exposes agent packages.
"""

from __future__ import annotations

from vidbyte.harnesses.client import HarnessClient
from vidbyte.harnesses.competitor_growth import CompetitorGrowthHarness, CompetitorGrowthAnalysis

__all__ = [
    "HarnessClient",
    "CompetitorGrowthHarness",
    "CompetitorGrowthAnalysis",
]

