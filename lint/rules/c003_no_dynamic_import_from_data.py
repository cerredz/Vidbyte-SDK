"""FILE: lint/rules/c003_no_dynamic_import_from_data.py

PURPOSE: Detect import targets computed from runtime data.
ROLE IN CODEBASE: Enforces fixed import and registry boundaries as C003.
ARCHITECTURE NOTE: Performs a side-effect-free AST scan over tracked SDK source.
FUNCTION INVENTORY: NoDynamicImportFromDataRule identifies and explains dynamic import calls.
COMMON MODIFICATION PATTERNS: Keep import forms and literal handling aligned; rerun C003.
WHAT NOT TO DO: Do not execute imported modules or narrow the security boundary to one folder.
KNOWN EDGE CASES: Calls without a positional module name are not considered dynamic targets.
RELATED DOCS: docs/design/sdk-lint-contract-rules.md
TESTS: Exercised by python lint/run.py --rule C003.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule


class NoDynamicImportFromDataRule(Rule):
    """Reject non-literal module names passed to import functions."""

    id = "C003"
    name = "no-dynamic-import-from-data"
    severity = "blocking"
    summary = "Import targets come from fixed source or registries, not runtime data."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans every parsed production module for the two dynamic import forms.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None:
                continue
            for node in ast.walk(source.tree):
                if isinstance(node, ast.Call) and self._is_dynamic_import_call(node) and self._first_arg_is_non_literal(node):
                    name = "__import__" if isinstance(node.func, ast.Name) else "import_module"
                    findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=node.lineno, source_line=source.line_at(node.lineno), symbol=name))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Directs the repair to the SDK's fixed registry boundary.
        return Diagnostic(
            what_happened=f"{finding.location()} calls {finding.symbol} with a non-literal module name.",
            why_blocked="A module name computed from a document or other runtime data lets that data choose which module-level code is imported.",
            how_to_fix="Resolve the same name through an explicit registry under vidbyte/lib/registries/. If the target is truly fixed, pass its string literal directly.",
            correct_examples=("Use a name-to-class registry for declarative configuration resolution.",),
            will_not_work=("Allowing a YAML/JSON ref to become an import path.", "Adding an import suppression or raising the baseline."),
            verify=self.verify_command(),
        )

    @staticmethod
    def _is_dynamic_import_call(node: ast.Call) -> bool:
        # Matches importlib.import_module and bare __import__ without executing imports.
        return (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module") or (isinstance(node.func, ast.Name) and node.func.id == "__import__")

    @staticmethod
    def _first_arg_is_non_literal(node: ast.Call) -> bool:
        # A missing positional argument is not a dynamic target for this check.
        return bool(node.args) and not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str))


RULE = NoDynamicImportFromDataRule()
