"""FILE: lint/core/registry.py

PURPOSE:
    Holds the fixed list of registered lint rules and rejects a duplicate
    rule id at import time rather than at run time.
ROLE IN CODEBASE:
    Consulted by lint/core/runner.py to resolve which rule classes to run,
    and by lint/run.py to validate a --rule argument against real ids.
COMMON MODIFICATION PATTERNS:
    Adding a new rule means adding one import and one entry to _RULES;
    nothing else in this file changes.
RELATED DOCS:
    docs/design/sdk-lint-python-correctness.md
    docs/design/sdk-lint-contract-rules.md
"""

from __future__ import annotations

from lint.core.rule import LintConfigurationError, LintRule
from lint.rules.c001_settings_class_configuration_error_placement import SettingsClassConfigurationErrorPlacementRule
from lint.rules.c002_duplicate_inline_bool_guard_validation import DuplicateInlineBoolGuardValidationRule
from lint.rules.c003_no_dynamic_import_from_data import NoDynamicImportFromDataRule
from lint.rules.c004_operation_pricing_rate_floor import OperationPricingRateFloorRule
from lint.rules.c005_cost_arithmetic_site_parity import CostArithmeticSiteParityRule
from lint.rules.s001_python_correctness_foundation import PythonCorrectnessFoundationRule

_RULES: tuple[type[LintRule], ...] = (
    PythonCorrectnessFoundationRule,
    SettingsClassConfigurationErrorPlacementRule,
    DuplicateInlineBoolGuardValidationRule,
    NoDynamicImportFromDataRule,
    OperationPricingRateFloorRule,
    CostArithmeticSiteParityRule,
)

if len({rule.rule_id for rule in _RULES}) != len(_RULES):
    raise LintConfigurationError("Duplicate rule_id registered in lint/core/registry.py.")


class RuleRegistry:
    """The fixed, compile-time-checked set of registered lint rules."""

    @staticmethod
    def all_rules() -> tuple[type[LintRule], ...]:
        # Returns every registered rule class, in registration order.
        return _RULES

    @staticmethod
    def by_id(rule_id: str) -> type[LintRule]:
        # Returns the registered rule class matching rule_id, or raises with the valid catalogue.
        for rule in _RULES:
            if rule.rule_id == rule_id:
                return rule
        valid = ", ".join(sorted(rule.rule_id for rule in _RULES))
        raise LintConfigurationError(f"Unknown rule id {rule_id!r}. Registered rules: {valid}.")


__all__ = ["RuleRegistry"]
