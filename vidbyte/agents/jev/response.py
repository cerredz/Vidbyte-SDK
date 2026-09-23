"""FILE: vidbyte/agents/jev/response.py

PURPOSE: Defines the compact structured response state maintained across one JevAgent run.
ROLE IN CODEBASE: JevRuntime records preset evidence, clarification state, final output, and decision usage here before exposing it in agent metadata.
ARCHITECTURE NOTE: JevResponse has only the five stable run-level fields; preset-specific detail stays nested in typed JevPresetResult values.
COMMON MODIFICATION PATTERNS: Extend JevPresetResult when a registered preset needs additional evidence without widening JevResponse.
KNOWN EDGE CASES: A fail-open preflight has an unavailable result with no score; a disabled preflight has no preset results.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_preflight.py and scripts/test-jev-preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from vidbyte.agents.pricing import JevUsage
from vidbyte.lib.dataclasses.jev import JevAnswer


@dataclass(frozen=True, slots=True)
class JevPresetResult:
    """The score and evidence produced for one enabled preflight preset."""

    score: float | None
    answers: Mapping[str, JevAnswer] = field(default_factory=dict)
    available: bool = True


@dataclass(slots=True)
class JevResponse:
    """Run-local Jev state returned through the ordinary agent response metadata."""

    input: str
    output: str | None = None
    results: dict[str, JevPresetResult] = field(default_factory=dict)
    needs_clarification: bool = False
    usage: JevUsage | None = None


__all__ = ["JevPresetResult", "JevResponse"]
