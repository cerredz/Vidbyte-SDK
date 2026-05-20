from __future__ import annotations

from enum import Enum


class BudgetPreset(str, Enum):
    """Named budget presets for strategy context construction."""

    TIGHT = "tight"
    BALANCED = "balanced"
    EXPLORATORY = "exploratory"
    UNBOUNDED = "unbounded"


class PermissionPreset(str, Enum):
    """Named permission presets for strategy context construction."""

    SANDBOXED = "sandboxed"
    READ_ONLY = "read_only"
    TOOLS_ONLY = "tools_only"
    TRUSTED = "trusted"
