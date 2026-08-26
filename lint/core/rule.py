"""FILE: lint/core/rule.py

PURPOSE:
    Defines the shared contract every lint rule implements and the two error
    types the whole lint suite raises for configuration and analyzer failures.
ROLE IN CODEBASE:
    Imported by lint/core/registry.py (to type the registry), by every module
    under lint/rules/ (to satisfy the protocol), and by lint/core/discovery.py,
    ruff.py, baseline.py, runner.py, and run.py (for the two error types).
FUNCTION INVENTORY:
    LintRule: Protocol a rule module's class must satisfy. A rule with a
        non-empty ruff_selectors filters the shared Ruff findings in find();
        a pure-AST rule sets ruff_selectors to () and parses files itself.
    LintConfigurationError: Raised for a setup problem (bad path, bad
        baseline file, unknown rule id) that a human or agent must fix
        before the suite can run at all.
    LintAnalyzerError: Raised when an external analyzer (Ruff) fails to run
        or returns output the suite cannot parse.
WHAT NOT TO DO IN THIS FILE:
    Do not add analyzer-specific logic here; this module only defines the
    contract and error vocabulary shared across analyzers.
RELATED DOCS:
    docs/design/sdk-lint-python-correctness.md
    docs/design/sdk-lint-contract-rules.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from lint.core.diagnostic import Finding, RuleDiagnostic
    from lint.core.ruff import RuffFinding


class LintConfigurationError(RuntimeError):
    """A lint suite setup problem the caller must fix before rerunning."""


class LintAnalyzerError(RuntimeError):
    """An external analyzer failed to run or returned unparsable output."""


class LintRule(Protocol):
    """Contract every registered lint rule module's class satisfies."""

    rule_id: ClassVar[str]
    ruff_selectors: ClassVar[tuple[str, ...]]

    @staticmethod
    def diagnostic() -> RuleDiagnostic:
        # Returns this rule's fixed agent-facing summary/impact/repair text.
        ...

    @staticmethod
    def find(files: tuple[Path, ...], ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]:
        # Returns this rule's fully-formed findings: Ruff-backed rules filter
        # ruff_findings; pure-AST rules parse files themselves and ignore it.
        ...
