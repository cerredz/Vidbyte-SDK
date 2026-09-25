"""FILE: vidbyte/agents/jev/presets.py

PURPOSE: Declares the named preflight capabilities callers may enable on JevAgent.
ROLE IN CODEBASE: JevAgentSettings normalizes these values and JevRuntime dispatches their fixed policies.
ARCHITECTURE NOTE: The enum exposes product capabilities while question text and decisions remain internal.
COMMON MODIFICATION PATTERNS: Add a named enum member for each supported capability; do not expose caller-authored questions.
KNOWN EDGE CASES: The TOOL_SELECTOR preset can be enabled without credentials; missing credentials are handled at run time.
RELATED DOCS: docs/design/jev-tool-selector.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_tool_selector.py.
"""

from __future__ import annotations

from enum import StrEnum


class JevPreflightPreset(StrEnum):
    """Named Jev preflight capabilities supported by JevAgent."""

    TOOL_SELECTOR = "tool_selector"


__all__ = ["JevPreflightPreset"]
