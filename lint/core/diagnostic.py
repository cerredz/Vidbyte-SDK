"""FILE: lint/core/diagnostic.py

PURPOSE:
    Defines one rule's typed finding shape and renders it into the
    agent-facing prose the repo's field guide requires.
ROLE IN CODEBASE:
    Findings are built by lint/core/runner.py from RuffFinding plus a rule
    id; rendering is called by lint/run.py for both text and JSON output.
WHAT NOT TO DO IN THIS FILE:
    Do not put analyzer-invocation logic here; this module only shapes and
    renders data that already exists.
RELATED DOCS:
    docs/design/sdk-lint-python-correctness.md
    field-guide/vidbyte-sdk/diagnostic-context.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Finding:
    """One rule's finding: a Ruff code at one location, tied to its rule id."""

    rule_id: str
    code: str
    file: Path
    line: int
    column: int
    message: str


@dataclass(frozen=True, slots=True)
class RuleDiagnostic:
    """A rule's fixed agent-facing explanation: what, why, how, and how to verify."""

    summary: str
    impact: str
    repair: str
    verify_command: str


class DiagnosticRenderer:
    """Renders a Finding plus its rule's RuleDiagnostic as text or JSON."""

    @staticmethod
    def render_text(finding: Finding, diagnostic: RuleDiagnostic) -> str:
        # Renders the four-section WHAT/WHY/HOW/VERIFY diagnostic for one finding.
        location = f"{finding.file}:{finding.line}:{finding.column}"
        return (
            f"[{finding.rule_id} {finding.code}] {location}\n"
            f"WHAT HAPPENED: {finding.message} {diagnostic.summary}\n"
            f"WHY THIS IS BLOCKED: {diagnostic.impact}\n"
            f"HOW TO FIX: {diagnostic.repair}\n"
            f"VERIFY: {diagnostic.verify_command}"
        )

    @staticmethod
    def render_json(finding: Finding) -> dict[str, object]:
        # Returns a flat, JSON-safe mapping of one finding's fields.
        return {
            "rule_id": finding.rule_id,
            "code": finding.code,
            "file": str(finding.file),
            "line": finding.line,
            "column": finding.column,
            "message": finding.message,
        }


__all__ = ["DiagnosticRenderer", "Finding", "RuleDiagnostic"]
