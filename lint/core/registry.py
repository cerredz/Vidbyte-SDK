"""FILE: lint/core/registry.py

PURPOSE: Defines the rule contract and ordered S001-S021 catalogue.
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

RULE_MODULES = tuple(f"lint.rules.s{number:03d}_{name}" for number, name in (
    (1, "python_correctness_foundation"), (2, "exception_cause_chaining"), (3, "strict_zip"), (4, "timezone_aware_datetime"),
    (5, "immutable_class_defaults"), (6, "async_task_ownership"), (7, "public_function_annotations"), (8, "bounded_function_complexity"),
    (9, "staged_mypy_contracts"), (10, "transport_parity"), (11, "raw_http_client_ownership"), (12, "explicit_outbound_timeout"),
    (13, "bounded_untrusted_responses"), (14, "provider_model_registry_parity"), (15, "public_export_integrity"), (16, "typed_boundary_errors"),
    (17, "no_raw_exception_disclosure"), (18, "priced_operation_attempts"), (19, "cancellation_propagation"), (20, "readme_file_index_parity"),
    (21, "class_bound_registry_helpers"),
))


class RuleSelectionError(RuntimeError):
    """Requested rule ID does not exist or the catalogue contains duplicates."""


class Rule:
    """Base contract implemented by every independently baselined rule."""

    id = ""
    name = ""
    severity = "blocking"
    summary = (
        "This rule protects one named contract in the SDK source tree. "
        "It turns a structural or analyzer fact into a stable finding that a coding agent can locate. "
        "The finding remains independent from unrelated policies so its baseline and repair path stay legible. "
        "A rule is complete only when its detection, consequence, repair guidance, and verification command agree."
    )
    impact = (
        "A violation means that an SDK assumption is no longer mechanically trustworthy. "
        "The immediate symptom may appear in a caller, provider, tool, or packaging step rather than at the violating line. "
        "That distance makes the defect expensive to diagnose when the rule reports only a count or a generic message. "
        "The diagnostic therefore explains the downstream failure before a maintainer chooses a repair."
    )
    repair = (
        "Start from the reported path, line, symbol, and rule-specific invariant. "
        "Apply the smallest change that restores the canonical contract at its owning boundary. "
        "Keep the implementation explicit and preserve neighboring behavior instead of weakening the analyzer or raising the baseline. "
        "Run the focused rule first, then the repository gate that exercises the affected boundary."
    )
    examples: tuple[str, ...] = ()
    will_not_work: tuple[str, ...] = ()

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
