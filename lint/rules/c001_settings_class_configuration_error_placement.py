"""FILE: lint/rules/c001_settings_class_configuration_error_placement.py

PURPOSE: Detect direct ConfigurationError raises in plain *Settings classes.
ROLE IN CODEBASE: Enforces dataclass-owned configuration validation as C001.
ARCHITECTURE NOTE: Uses only the shared tracked-source AST catalogue; never imports SDK code.
FUNCTION INVENTORY: SettingsClassConfigurationErrorPlacementRule scans and explains findings.
COMMON MODIFICATION PATTERNS: Change the class-shape predicate and diagnostic together; rerun C001.
WHAT NOT TO DO: Do not broaden the Settings suffix or suppress findings for convenience.
KNOWN EDGE CASES: Dataclass decorators and nested method control flow are handled statically.
RELATED DOCS: docs/design/sdk-lint-contract-rules.md
TESTS: Exercised by python lint/run.py --rule C001.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

_CONFIGURATION_ERROR_NAME = "ConfigurationError"
_SETTINGS_SUFFIX = "Settings"


class SettingsClassConfigurationErrorPlacementRule(Rule):
    """Reject direct ConfigurationError raises in plain *Settings classes."""

    id = "C001"
    name = "settings-class-configuration-error-placement"
    severity = "blocking"
    summary = "Plain *Settings classes delegate validation to frozen dataclasses."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans parsed production modules without importing SDK runtime code.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is not None:
                findings.extend(self._scan_module(source))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the class and method that must move validation to a dataclass.
        return Diagnostic(
            what_happened=f"{finding.location()} {finding.symbol} raises ConfigurationError directly in a plain *Settings class.",
            why_blocked="Validation scattered across a plain settings class can be skipped by a future call path, leaving downstream code without a provably valid configuration value.",
            how_to_fix="Define a frozen, slotted dataclass in vidbyte/lib/dataclasses/ whose __post_init__ owns the checks and raises ConfigurationError. Have the settings adapter construct and retain that validated value.",
            correct_examples=("vidbyte/lib/dataclasses/agents.py - PauseDuration shows the validated dataclass shape.",),
            will_not_work=("Moving the raise into __init__ without introducing the validated dataclass.", "Adding a lint suppression or increasing the baseline."),
            verify=self.verify_command(),
        )

    @classmethod
    def _scan_module(cls, source: SourceFile) -> list[Finding]:
        # Finds every direct ConfigurationError raise in each matching class method.
        findings: list[Finding] = []
        for node in ast.walk(source.tree):
            if isinstance(node, ast.ClassDef) and cls._is_plain_settings_class(node):
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for child in ast.walk(member):
                            if isinstance(child, ast.Raise) and cls._raises_configuration_error(child):
                                findings.append(Finding(rule_id=cls.id, rel_path=source.rel, line=child.lineno, source_line=source.line_at(child.lineno), symbol=f"{node.name}.{member.name}", extra={"class": node.name, "method": member.name}))
        return findings

    @staticmethod
    def _is_plain_settings_class(node: ast.ClassDef) -> bool:
        # Matches only the literal Settings suffix and non-dataclass classes.
        if not node.name.endswith(_SETTINGS_SUFFIX):
            return False
        return not any(SettingsClassConfigurationErrorPlacementRule._is_dataclass_decorator(item) for item in node.decorator_list)

    @staticmethod
    def _is_dataclass_decorator(decorator: ast.expr) -> bool:
        # Accepts both @dataclass and @dataclasses.dataclass forms.
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        return (isinstance(target, ast.Name) and target.id == "dataclass") or (isinstance(target, ast.Attribute) and target.attr == "dataclass")

    @staticmethod
    def _raises_configuration_error(node: ast.Raise) -> bool:
        # Matches a direct ConfigurationError(...) constructor, not unrelated errors.
        if node.exc is None:
            return False
        target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        return isinstance(target, ast.Name) and target.id == _CONFIGURATION_ERROR_NAME


RULE = SettingsClassConfigurationErrorPlacementRule()
