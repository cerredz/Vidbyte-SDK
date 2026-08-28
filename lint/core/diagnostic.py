"""FILE: lint/core/diagnostic.py

PURPOSE: Defines immutable finding facts and agent-facing repair diagnostics.
ROLE IN CODEBASE: Gives every analyzer and semantic rule one output contract.
ARCHITECTURE NOTE: Findings contain facts; Diagnostic contains repair prose.
FUNCTION INVENTORY: Finding.location() renders a stable file anchor.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by every python lint/run.py invocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Finding:
    """One rule violation at a stable repository location."""

    rule_id: str
    rel_path: str
    line: int
    source_line: str = ""
    symbol: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def location(self) -> str:
        # Returns a clickable relative path and positive source line.
        return f"{self.rel_path}:{max(1, self.line)}"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Complete consequence and repair guidance for one finding."""

    what_happened: str
    why_blocked: str
    how_to_fix: str
    correct_examples: tuple[str, ...] = ()
    will_not_work: tuple[str, ...] = ()
    verify: str = ""
