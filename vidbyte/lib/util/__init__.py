"""Context Protocol Header

Description:
    General-purpose, domain-agnostic helper utilities shared across the SDK.
Purpose:
    Houses static-method helper classes (e.g. MathHelper) that have no
    dependency on any specific SDK feature — agents, sessions, harnesses, or
    otherwise. Code belongs here only when it would be equally at home in an
    unrelated project.
Architecture:
    - math.py: MathHelper, numeric aggregation (mean, percentile, max, argmax).
Relations:
    Consumed by vidbyte.agents.speed.tracker and any future SDK code that needs
    the same general-purpose statistics.
"""

from __future__ import annotations

from vidbyte.lib.util.math import MathHelper

__all__ = ["MathHelper"]
