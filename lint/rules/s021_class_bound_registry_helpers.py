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
    summary = (
        "This rule keeps public behavior for a registry beside the registry state that gives that behavior meaning. "
        "It scans declared registry modules for public module-level helpers while allowing private parsing leaves and dunder exports. "
        "A finding identifies a helper whose ownership is split from the class that callers must discover to understand the registry contract. "
        "The rule makes lookup, validation, normalization, and registry data one navigable public surface."
    )
    impact = (
        "A public free function beside registry data creates two competing discovery surfaces for one conceptual responsibility. "
        "Callers may miss the canonical class, duplicate validation logic, or pass state through an API that does not visibly own it. "
        "That split becomes more damaging as provider and model catalogues gain aliases, defaults, or compatibility rules. "
        "The resulting architecture is harder for agents to navigate and easier to change inconsistently."
    )
    repair = (
        "Identify the registry class whose state and invariants the helper reads or enforces. "
        "Move the public helper onto that class as a static method or class method, keeping unrelated parsing details private to the module. "
        "Update every caller to use the owning class and preserve the helper's input, output, error, and ordering behavior. "
        "Run the focused rule plus registry import, configuration, and caller checks after confirming the public export points at the class-owned surface."
    )
    examples = (
        "vidbyte/lib/registries/models.py - ProviderModelRegistry owns related lookup and validation behavior",
        "A @staticmethod or @classmethod called through the registry class at each public call site",
    )
    will_not_work = (
        "Moving the helper to a generic utils.py module and leaving registry ownership implicit.",
        "Renaming a cross-module public helper with a leading underscore without updating ownership and callers.",
    )

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
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} defines public module-level registry helper {finding.symbol}.", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = ClassBoundRegistryHelpersRule()
