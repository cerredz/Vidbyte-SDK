"""Context Protocol Header

Description:
    Exports handoff context primitive classes.
Purpose:
    Provides the public package entry point for base and prebuilt handoff specs.
Architecture:
    - base: Core Handoff primitive.
    - engineering / research / minimal: Prebuilt Handoff subclasses.
Relations:
    Re-exported by vidbyte.context and vidbyte root namespace.
Similar Files:
    - vidbyte/context/__init__.py: Wider context namespace exports.
"""

from __future__ import annotations

from vidbyte.context.handoff.base import Handoff
from vidbyte.context.handoff.engineering import EngineeringHandoff
from vidbyte.context.handoff.minimal import MinimalHandoff
from vidbyte.context.handoff.research import ResearchHandoff

__all__ = [
    "Handoff",
    "EngineeringHandoff",
    "MinimalHandoff",
    "ResearchHandoff",
]
