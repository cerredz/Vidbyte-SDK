"""FILE: lint/rules/s041_unspecified_encoding.py

PURPOSE: Defines S041 for file reads and writes without an explicit encoding.
ROLE IN CODEBASE: Makes SDK text behavior portable across developer and consumer platforms.
ARCHITECTURE NOTE: Detection is delegated to the cached Ruff adapter.
FUNCTION INVENTORY: Exports one Ruff-backed rule instance.
COMMON MODIFICATION PATTERNS: Change code, scope, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not rely on the host locale for persisted SDK text.
KNOWN EDGE CASES: Ruff owns the file-call classification and supported APIs.
RELATED DOCS: docs/design/agent-native-lint-rule-expansion.md
TESTS: Exercised by python lint/run.py --rule S041.
"""

from lint.core.ruff import RuffBackedRule


class UnspecifiedEncodingRule(RuffBackedRule):
    """Requires text file operations to state the encoding they expect."""

    id = "S041"
    name = "unspecified-encoding"
    summary = (
        "SDK file operations specify an encoding instead of inheriting the host locale. "
        "The default encoding can differ between a developer machine, CI, and a consumer deployment. "
        "That can corrupt prompts, manifests, cached sessions, or error text without changing the Python code path. "
        "Persisted text needs an explicit portable boundary."
    )
    codes = frozenset({"PLW1514"})
    impact = (
        "Locale-dependent decoding can turn valid UTF-8 SDK assets into errors or altered content. "
        "The failure may affect only a user's language, provider response, or operating system. "
        "It is therefore hard to reproduce from a single test environment. "
        "Explicit encoding keeps file interchange deterministic."
    )
    repair = (
        "Pass the intended encoding explicitly, normally encoding='utf-8' for repository and wire text. "
        "Choose another encoding only when the file format contract documents it. "
        "Do not suppress the warning or assume every deployment uses the same locale. "
        "Run the focused rule and read/write a representative non-ASCII fixture after the edit."
    )


RULE = UnspecifiedEncodingRule()
