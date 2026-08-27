"""FILE: lint/rules/s021_class_bound_registry_helpers.py

PURPOSE: Keeps public registry behavior on the class that owns registry state.
ROLE IN CODEBASE: Makes related lookup/validation helpers discoverable from one owner.
ARCHITECTURE NOTE: Private module parsers and dunder exports remain allowed.
FUNCTION INVENTORY: ClassBoundRegistryHelpersRule scans module-level public functions.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: field-guide/vidbyte-sdk/class-bound-helpers.md
TESTS: Exercised by python lint/run.py --rule S021.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

REGISTRY_PREFIX = "vidbyte/lib/registries/"


class ClassBoundRegistryHelpersRule(Rule):
    """Requires public registry helpers to be static/class methods on their owner."""

    id = "S021"
    name = "class-bound-registry-helpers"
    severity = "blocking"
    summary = "Registry modules expose behavior through owning registry classes."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans only top-level statements so class methods and private parsers stay valid.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not source.rel.startswith(REGISTRY_PREFIX) or source.rel.endswith("/__init__.py"):
                continue
            for node in source.tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                    findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol=node.name, extra={"function": node.name}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Moves related behavior beside its registry data without creating a generic utility module.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} defines public module-level registry helper {finding.symbol}.", why_blocked="Registry state and its lookup/validation behavior become split across two discovery surfaces, so callers and future agents miss the canonical path and recreate logic.", how_to_fix="Move the helper onto the owning registry class as @staticmethod or @classmethod, update callers to ClassName.method(...), and keep any unrelated private parsing leaf module-private.", correct_examples=("vidbyte/lib/registries/models.py - ProviderModelRegistry owns related lookup/validation methods",), will_not_work=("Moving the helper to a generic utils.py module.", "Renaming a cross-module public helper with a leading underscore without updating ownership."), verify=self.verify_command())


RULE = ClassBoundRegistryHelpersRule()
