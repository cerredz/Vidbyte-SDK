"""FILE: lint/core/registry.py

PURPOSE: Defines the rule contract and ordered SDK lint catalogue.
ROLE IN CODEBASE: Makes every rule independently selectable and rejects duplicate IDs.
ARCHITECTURE NOTE: Registry imports policy but never scans source itself.
FUNCTION INVENTORY: RuleRegistry.all()/select() return stable rule instances.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by focused and complete lint commands.
"""

from __future__ import annotations

import importlib

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog

RULE_MODULES = (
    "lint.rules.a001_agent_readable_file_headers",
    "lint.rules.a002_intent_comments",
    "lint.rules.a003_context_rich_error_packets",
    "lint.rules.a005_typed_dependency_seams",
    "lint.rules.a006_directed_dependency_graph",
    "lint.rules.a007_operational_constants",
    "lint.rules.a008_library_stdout_boundary",
    "lint.rules.s001_python_correctness_foundation",
    "lint.rules.s002_exception_cause_chaining",
    "lint.rules.s003_strict_zip",
    "lint.rules.s004_timezone_aware_datetime",
    "lint.rules.s005_immutable_class_defaults",
    "lint.rules.s006_async_task_ownership",
    "lint.rules.s007_public_function_annotations",
    "lint.rules.s008_bounded_function_complexity",
    "lint.rules.s009_staged_mypy_contracts",
    "lint.rules.s010_transport_parity",
    "lint.rules.s011_raw_http_client_ownership",
    "lint.rules.s012_explicit_outbound_timeout",
    "lint.rules.s013_bounded_untrusted_responses",
    "lint.rules.s014_provider_model_registry_parity",
    "lint.rules.s015_public_export_integrity",
    "lint.rules.s016_typed_boundary_errors",
    "lint.rules.s017_no_raw_exception_disclosure",
    "lint.rules.s018_priced_operation_attempts",
    "lint.rules.s019_cancellation_propagation",
    "lint.rules.s020_readme_file_index_parity",
    "lint.rules.s021_class_bound_registry_helpers",
    "lint.rules.s024_maximum_control_flow_nesting",
)


class RuleSelectionError(RuntimeError):
    """Requested rule ID does not exist or the catalogue contains duplicates."""


class Rule:
    """Base contract implemented by every independently baselined rule."""

    id = ""
    name = ""
    severity = "blocking"
    summary = ""

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Produces every finding without mutating source or importing the package.
        raise NotImplementedError

    def explain(self, finding: Finding) -> Diagnostic:
        # Produces a self-contained repair diagnostic for one finding.
        raise NotImplementedError

    def verify_command(self) -> str:
        # Returns the exact focused command used after repairing this rule.
        return f"python lint/run.py --rule {self.id}"


class RuleRegistry:
    """Loads the fixed rule catalogue once and serves stable selections."""

    def __init__(self) -> None:
        # Imports each module and validates non-empty unique IDs.
        self._rules = self._load()

    def all(self) -> tuple[Rule, ...]:
        # Returns every rule in stable lexical ID order.
        return self._rules

    def select(self, rule_id: str | None) -> tuple[Rule, ...]:
        # Returns one named rule or the complete catalogue with valid IDs on failure.
        if rule_id is None:
            return self.all()
        wanted = rule_id.upper()
        chosen = tuple(rule for rule in self._rules if rule.id == wanted)
        if not chosen:
            valid = ", ".join(rule.id for rule in self._rules)
            raise RuleSelectionError(f"Unknown SDK lint rule {wanted!r}. Valid rules: {valid}.")
        return chosen

    def _load(self) -> tuple[Rule, ...]:
        # Imports exported RULE objects and rejects duplicate/blank identifiers.
        rules = tuple(importlib.import_module(path).RULE for path in RULE_MODULES)
        seen: set[str] = set()
        for rule in rules:
            if not rule.id or rule.id in seen:
                raise RuleSelectionError(f"Duplicate or blank SDK lint rule ID {rule.id!r} in the registered catalogue.")
            seen.add(rule.id)
        return tuple(sorted(rules, key=lambda item: item.id))
