"""FILE: lint/rules/c003_no_dynamic_import_from_data.py

PURPOSE:
    Declares C003: importlib.import_module(...) or __import__(...) must be
    called with a string literal, never with a value computed from data.
ROLE IN CODEBASE:
    Registered by lint/core/registry.py. Pure-AST rule (ruff_selectors is
    empty); parses files itself via lint/core/parsing.PythonSourceParser.
ARCHITECTURE NOTE:
    Grounded in field-guide/vidbyte-sdk/declarative-config-resolution.md's
    stated threat model: "vidbyte/config's threat model forbids any document
    text reaching an import." Verified against the live tree: the only
    import_module/__import__ hit repo-wide is inside a markdown prompt
    template (not real source) and already passes a literal. This rule
    ships as a pure regression guard at zero current findings, not a fix
    for existing debt.
WHAT NOT TO DO IN THIS FILE:
    Do not scope this to only vidbyte/config/ -- the invariant "never
    import from computed data" is a general security boundary worth holding
    everywhere in the SDK, and scoping it narrower would add directory
    filtering for no precision benefit (there are zero violations to
    over-flag anywhere in the tree today).
RELATED DOCS:
    docs/design/sdk-lint-contract-rules.md
    field-guide/vidbyte-sdk/declarative-config-resolution.md
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, ClassVar

from lint.core.diagnostic import Finding, RuleDiagnostic
from lint.core.parsing import PythonSourceParser

if TYPE_CHECKING:
    from pathlib import Path

    from lint.core.ruff import RuffFinding


class NoDynamicImportFromDataRule:
    """C003: import_module/__import__ must take a literal module name."""

    rule_id: ClassVar[str] = "C003"
    ruff_selectors: ClassVar[tuple[str, ...]] = ()

    @staticmethod
    def diagnostic() -> RuleDiagnostic:
        # Returns C003's fixed summary/impact/repair/verify-command text.
        return RuleDiagnostic(
            summary=(
                "`importlib.import_module(...)` or `__import__(...)` is called with a first "
                "argument that is not a string literal -- meaning the module name comes from "
                "a variable or expression computed at runtime rather than being fixed in "
                "source. `vidbyte/config`'s stated threat model "
                "(field-guide/vidbyte-sdk/declarative-config-resolution.md) forbids any "
                "parsed document's text from reaching an import."
            ),
            impact=(
                "A dynamic import driven by external data (a YAML `ref`, a harness spec field, "
                "any parsed document value) is a code-execution boundary: whoever controls that "
                "data controls which module gets imported and, transitively, what module-level "
                "code runs. This is exactly the shape of vulnerability declarative config "
                "resolution exists to close off by design -- refs resolve through a fixed "
                "name-to-class registry, never through an import driven by the document itself."
            ),
            repair=(
                "Replace the dynamic import with a lookup in the appropriate registry under "
                "`vidbyte/lib/registries/` (see `vidbyte/lib/registries/components.py` for the "
                "existing name-to-class catalog pattern), keyed by the same string that would "
                "otherwise have been passed to `import_module`. If the module name is genuinely "
                "always a fixed, hardcoded string and this is a false positive, pass it as a "
                "literal directly in the call rather than through an intermediate variable, "
                "which also makes the call self-evidently safe to a reviewer."
            ),
            verify_command="python lint/run.py --rule C003",
        )

    @staticmethod
    def find(files: tuple[Path, ...], ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]:
        # Parses every file and flags each dynamic-import call with a non-literal first argument.
        findings: list[Finding] = []
        for path in files:
            module = PythonSourceParser.parse(path)
            if module is None:
                continue
            for node in ast.walk(module):
                if isinstance(node, ast.Call) and NoDynamicImportFromDataRule._is_dynamic_import_call(node) and NoDynamicImportFromDataRule._first_arg_is_non_literal(node):
                    findings.append(
                        Finding(
                            rule_id="C003",
                            code="C003",
                            file=path,
                            line=node.lineno,
                            column=node.col_offset,
                            message="Dynamic import called with a non-literal module name; module identity must come from a registry, not computed data.",
                        )
                    )
        return tuple(findings)

    @staticmethod
    def _is_dynamic_import_call(node: ast.Call) -> bool:
        # True for importlib.import_module(...) or bare __import__(...).
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "import_module":
            return True
        return isinstance(func, ast.Name) and func.id == "__import__"

    @staticmethod
    def _first_arg_is_non_literal(node: ast.Call) -> bool:
        # True when the call has a first argument and it is not a string constant.
        if not node.args:
            return False
        first = node.args[0]
        return not (isinstance(first, ast.Constant) and isinstance(first.value, str))


__all__ = ["NoDynamicImportFromDataRule"]
