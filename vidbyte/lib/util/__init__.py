"""FILE: vidbyte/lib/util/__init__.py

PURPOSE:
    Public surface for vidbyte/lib/util, the home for general-purpose,
    domain-agnostic helper classes that have no dependency on any specific
    SDK feature (agents, sessions, harnesses, or otherwise).

ROLE IN CODEBASE:
    Re-exports MathHelper and AsyncCapacityLimiter. Imported by
    vidbyte/agents/speed/tracker.py and any future SDK code that needs the
    same general-purpose statistics.

ARCHITECTURE NOTE:
    A thin package export, mirroring how vidbyte/lib/enums/__init__.py and
    vidbyte/lib/dataclasses/__init__.py re-export their sibling modules.

FUNCTION INVENTORY:
    No functions of its own; re-exports shared statistics and concurrency helpers.

COMMON MODIFICATION PATTERNS:
    Add a new general-purpose helper class as its own module in this folder,
    then re-export it here. Code belongs here only when it would be equally
    at home in an unrelated project with no SDK dependencies.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add feature-specific logic (agent, session, or harness
       behavior); that belongs in the owning feature package.
    2. Do not add import-time side effects.

KNOWN EDGE CASES:
    None.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-speed-tracking.md

TESTS:
    tests/test_agent_speed.py covers MathHelper; tests/codex_control covers capacity admission.
"""

from __future__ import annotations

from vidbyte.lib.util.concurrency import AsyncCapacityLimiter
from vidbyte.lib.util.math import MathHelper

__all__ = ["AsyncCapacityLimiter", "MathHelper"]
