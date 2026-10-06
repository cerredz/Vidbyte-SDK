"""FILE: lint/rules/c002_duplicate_inline_bool_guard_validation.py

PURPOSE: Detect repeated meaningful isinstance(..., bool) validation identities.
ROLE IN CODEBASE: Enforces one validation owner for duplicated bool guards as C002.
ARCHITECTURE NOTE: Groups facts from the shared tracked-source AST catalogue without importing SDK code.
FUNCTION INVENTORY: DuplicateInlineBoolGuardValidationRule collects, groups, and explains findings.
COMMON MODIFICATION PATTERNS: Adjust the identity exclusions and diagnostics together; rerun C002.
WHAT NOT TO DO: Do not include generic names or treat the baseline as a suppression mechanism.
KNOWN EDGE CASES: One identity per function is counted; distinct functions remain separate occurrences.
RELATED DOCS: docs/design/sdk-lint-contract-rules.md
TESTS: Exercised by python lint/run.py --rule C002.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

_GENERIC_IDENTITIES = frozenset({"value", "raw", "data", "entry", "item", "obj", "setting", "x", "v", "val", "flag"})


@dataclass(frozen=True, slots=True)
class _Occurrence:
    """One meaningful isinstance(value, bool) occurrence."""

    identity: str
    rel_path: str
    function: str
    line: int
    source_line: str


class DuplicateInlineBoolGuardValidationRule(Rule):
    """Reject repeated inline bool guards for the same meaningful identity."""

    id = "C002"
    name = "duplicate-inline-bool-guard-validation"
    severity = "blocking"
    summary = "Meaningful bool-guard validation is centralized instead of copied."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Groups one occurrence per function by identity and reports every duplicate site.
        groups: dict[str, list[_Occurrence]] = {}
        for source in catalog.python_files():
            if source.tree is None:
                continue
            for node in ast.walk(source.tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for occurrence in self._occurrences_in_function(source, node):
                        groups.setdefault(occurrence.identity, []).append(occurrence)
        findings: list[Finding] = []
        for identity, occurrences in sorted(groups.items()):
            if len(occurrences) >= 2:
                findings.extend(self._findings_for_group(identity, occurrences))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Points to the other function sites that need one canonical validator.
        return Diagnostic(
            what_happened=f"{finding.location()} validates '{finding.symbol}' with isinstance(..., bool), and the same meaningful identity is guarded elsewhere: {finding.extra.get('other_sites', 'see focused findings')}.",
            why_blocked="Copied validation rules drift when one call site changes its accepted range or error behavior while another keeps the old contract.",
            how_to_fix="Define one frozen, slotted dataclass in vidbyte/lib/dataclasses/ whose __post_init__ owns this validation, then construct it at each flagged boundary.",
            correct_examples=("vidbyte/lib/dataclasses/agents.py - PauseDuration is the local validated-dataclass precedent.",),
            will_not_work=("Centralizing unrelated generic value/raw/data checks just because they share a variable name.", "Adding a suppression or raising the baseline."),
            verify=self.verify_command(),
        )

    @classmethod
    def _occurrences_in_function(cls, source: SourceFile, function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[_Occurrence]:
        # Deduplicates one identity within a function while preserving distinct functions.
        occurrences: list[_Occurrence] = []
        seen: set[str] = set()
        for node in ast.walk(function):
            identity = cls._bool_guard_identity(node)
            if identity is None or identity in _GENERIC_IDENTITIES or identity in seen:
                continue
            seen.add(identity)
            occurrences.append(_Occurrence(identity=identity, rel_path=source.rel, function=function.name, line=node.lineno, source_line=source.line_at(node.lineno)))
        return occurrences

    @staticmethod
    def _bool_guard_identity(node: ast.AST) -> str | None:
        # Returns the Name or Attribute identity used as isinstance's first argument.
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "isinstance"):
            return None
        if len(node.args) != 2 or not (isinstance(node.args[1], ast.Name) and node.args[1].id == "bool"):
            return None
        target = node.args[0]
        if isinstance(target, ast.Name):
            return target.id
        return target.attr if isinstance(target, ast.Attribute) else None

    def _findings_for_group(self, identity: str, occurrences: list[_Occurrence]) -> list[Finding]:
        # Emits one actionable finding per duplicated validation site.
        findings: list[Finding] = []
        for occurrence in occurrences:
            others = sorted(f"{item.rel_path}:{item.line} ({item.function})" for item in occurrences if item != occurrence)
            findings.append(Finding(rule_id=self.id, rel_path=occurrence.rel_path, line=occurrence.line, source_line=occurrence.source_line, symbol=identity, extra={"other_sites": ", ".join(others), "function": occurrence.function}))
        return findings


RULE = DuplicateInlineBoolGuardValidationRule()
