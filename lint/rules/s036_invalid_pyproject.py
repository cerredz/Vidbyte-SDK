"""FILE: lint/rules/s036_invalid_pyproject.py

PURPOSE: Defines S036 for invalid or inconsistent pyproject.toml metadata.
ROLE IN CODEBASE: Keeps SDK packaging metadata parseable and buildable.
ARCHITECTURE NOTE: Ruff scans pyproject.toml explicitly through the shared adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not hide packaging metadata errors from the lint gate.
KNOWN EDGE CASES: Findings may have no Python source line because they belong to TOML.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S036.
"""

from lint.core.ruff import RuffBackedRule


class InvalidPyprojectRule(RuffBackedRule):
    """Requires project metadata to satisfy Ruff's pyproject validation."""

    id = "S036"
    name = "invalid-pyproject"
    summary = (
        "The SDK's pyproject.toml remains valid for the pinned packaging and tooling contract. "
        "Malformed metadata can pass source review while failing a build or dependency installation. "
        "An invalid field can also make the published wheel differ from local expectations. "
        "Treat project metadata as executable configuration that needs the same review discipline as Python."
    )
    codes = frozenset({"RUF200"})
    impact = (
        "Packaging metadata controls how consumers install, build, and discover the SDK. "
        "A typo or incompatible value can block release automation or silently omit package behavior. "
        "The failure often appears outside the developer's normal runtime test path. "
        "Keeping pyproject.toml valid protects the distribution boundary."
    )
    repair = (
        "Read Ruff's exact TOML diagnostic and correct the named field using the project's supported metadata shape. "
        "Keep the change consistent with the existing build-system and package configuration. "
        "Do not add a per-file ignore or move invalid metadata into an unvalidated side file. "
        "Run the focused rule and the package build gate after the edit."
    )


RULE = InvalidPyprojectRule()
