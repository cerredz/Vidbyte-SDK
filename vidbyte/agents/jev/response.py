"""FILE: vidbyte/agents/jev/response.py

PURPOSE: Defines run-local response records for Jev preflight decisions.
ROLE IN CODEBASE: JevRuntime maps decision answers into these records and exposes them in AgentResult metadata.
ARCHITECTURE NOTE: Records expose category flags and usage without retaining or echoing supplied input content.
COMMON MODIFICATION PATTERNS: Add preset-specific typed results while keeping sensitive payload text out of response metadata.
KNOWN EDGE CASES: An unavailable result uses None flags; a known positive remains true even if other answers are missing.
RELATED DOCS: docs/design/jev-preflight-sensitive-data.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_sensitive_preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from vidbyte.agents.pricing import JevUsage


@dataclass(frozen=True, slots=True)
class JevSecurityResult:
    """Sensitive-data flags for one supplied request."""

    available: bool
    flags: Mapping[str, bool | None]
    any_sensitive: bool | None

    def __post_init__(self) -> None:
        # Freezes flags so callers cannot mutate evidence after the response is returned.
        object.__setattr__(self, "flags", MappingProxyType(dict(self.flags)))


@dataclass(slots=True)
class JevResponse:
    """Run-local Jev state returned through ordinary agent response metadata."""

    results: dict[str, JevSecurityResult] = field(default_factory=dict)
    usage: JevUsage | None = None


__all__ = ["JevResponse", "JevSecurityResult"]
