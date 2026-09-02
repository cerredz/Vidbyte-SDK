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
    "lint.rules.c001_settings_class_configuration_error_placement",
    "lint.rules.c002_duplicate_inline_bool_guard_validation",
    "lint.rules.c003_no_dynamic_import_from_data",
    "lint.rules.c004_operation_pricing_rate_floor",
    "lint.rules.c005_cost_arithmetic_site_parity",
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
    "lint.rules.s025_model_facing_description_depth",
    "lint.rules.s026_pairwise_zip",
    "lint.rules.s027_mutable_dataclass_default",
    "lint.rules.s028_dataclass_default_call",
    "lint.rules.s029_unnecessary_first_element_allocation",
    "lint.rules.s030_quadratic_list_summation",
    "lint.rules.s031_assignment_in_assert",
    "lint.rules.s032_unnecessary_key_check",
    "lint.rules.s033_mutable_dict_fromkeys",
    "lint.rules.s034_ambiguous_pytest_raises_match",
    "lint.rules.s035_unused_noqa",
    "lint.rules.s036_invalid_pyproject",
    "lint.rules.s037_blanket_type_ignore",
    "lint.rules.s038_blanket_noqa",
    "lint.rules.s039_banned_api_policy",
    "lint.rules.s040_relative_imports",
    "lint.rules.s041_unspecified_encoding",
    "lint.rules.s042_raise_vanilla_class",
    "lint.rules.s043_verbose_log_message",
    "lint.rules.s044_logging_f_string",
    "lint.rules.s045_async_function_with_timeout",
    "lint.rules.s046_blocking_http_call_in_async_function",
    "lint.rules.s047_blocking_open_in_async_function",
    "lint.rules.s048_blocking_sleep_in_async_function",
    "lint.rules.s049_unsafe_yaml_load",
    "lint.rules.s050_insecure_hash",
    "lint.rules.s051_modernized_import_and_syntax_hygiene",
    "lint.rules.s052_async_blocking_io",
    "lint.rules.s053_defensive_python_bugbear",
    "lint.rules.s054_bandit_security_subset",
    "lint.rules.s055_no_shell_subprocess",
    "lint.rules.s056_retryable_idempotent_methods",
    "lint.rules.s057_no_model_construct_without_review",
    "lint.rules.s058_forbid_unknown_fields_at_boundary",
    "lint.rules.s059_explicit_serialization_mode",
    "lint.rules.s060_typed_public_seam_mappings",
    "lint.rules.s061_bounded_safe_path",
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
