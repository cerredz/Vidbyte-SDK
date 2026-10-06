"""FILE: lint/rules/s049_unsafe_yaml_load.py

PURPOSE: Defines S049 for unsafe YAML deserialization calls.
ROLE IN CODEBASE: Keeps SDK configuration parsing from constructing arbitrary objects.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not treat a YAML document as trusted merely because it is local.
KNOWN EDGE CASES: Approved custom safe loaders require explicit boundary review.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S049.
"""

from lint.core.ruff import RuffBackedRule


class UnsafeYamlLoadRule(RuffBackedRule):
    """Requires YAML input to use a safe loader appropriate for untrusted data."""

    id = "S049"
    name = "unsafe-yaml-load"
    summary = (
        "SDK YAML parsing does not use a loader that can construct arbitrary Python objects from input. "
        "Configuration and prompt-adjacent files can be modified, supplied by users, or loaded from a provider workflow. "
        "Unsafe deserialization turns data parsing into code-construction capability. "
        "Use the repository-approved safe loader and preserve only the tags the format requires."
    )
    codes = frozenset({"S506"})
    impact = (
        "An unsafe YAML loader can execute or construct attacker-controlled objects during configuration parsing. "
        "The resulting compromise occurs before the SDK reaches its normal request or error boundaries. "
        "Even a currently local file can become untrusted when packaging, plugins, or model workflows provide its contents. "
        "Safe loading is a security boundary, not a parser preference."
    )
    repair = (
        "Use yaml.safe_load or the repository's explicitly reviewed safe custom loader with a narrow constructor set. "
        "Verify that required duplicate-key or schema behavior remains enforced without enabling arbitrary object construction. "
        "Do not suppress S506 because a file is expected to be local or because tests use trusted fixtures. "
        "Run the focused rule and the configuration security tests after the edit."
    )


RULE = UnsafeYamlLoadRule()
