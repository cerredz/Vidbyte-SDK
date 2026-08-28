"""FILE: lint/rules/s059_explicit_serialization_mode.py

PURPOSE: Requires every model_dump() call to declare its serialization mode explicitly.
ROLE IN CODEBASE: Keeps wire/persistence payloads from silently depending on Pydantic's Python-mode default.
ARCHITECTURE NOTE: Pure syntactic AST match on the method name and its keyword arguments.
FUNCTION INVENTORY: ExplicitSerializationModeRule scans every call for .model_dump( missing mode=.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S059.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule


class ExplicitSerializationModeRule(Rule):
    """Requires model_dump() calls to pass an explicit mode= keyword."""

    id = "S059"
    name = "explicit-serialization-mode"
    severity = "blocking"
    summary = "model_dump() calls declare mode= explicitly instead of relying on the Python-mode default."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Walks every call expression looking for model_dump( missing a mode= keyword.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None:
                continue
            for node in ast.walk(source.tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "model_dump" and not any(kw.arg == "mode" for kw in node.keywords):
                    findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol="model_dump"))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the call and the wire-vs-Python mode distinction it must choose.
        return Diagnostic(
            what_happened=f"{finding.rel_path}:{finding.line} calls model_dump() without an explicit mode= keyword.",
            why_blocked="model_dump()'s default mode='python' keeps native Python types (datetime, Enum, UUID) in the output, while mode='json' produces JSON-compatible primitives; a wire, persistence, or trace payload that silently depends on the default breaks the moment a nested model introduces a non-JSON-native field, and the breakage surfaces at the consumer, not at this call site.",
            how_to_fix="Add mode=\"json\" if this value crosses a wire/persistence/trace boundary, or mode=\"python\" if it deliberately stays in-process as native Python objects.",
            correct_examples=('vidbyte/sessions/serialization.py - .model_dump(mode="json") at the persistence boundary.', 'vidbyte/agents/algorithms/prosecutor_defender_judge.py - .model_dump(mode="json") at the trace boundary.'),
            will_not_work=("Adding mode=None, which is not a valid Pydantic mode and will raise at runtime.", "Wrapping the result in json.dumps() instead of choosing the correct mode."),
            verify=self.verify_command(),
        )


RULE = ExplicitSerializationModeRule()
