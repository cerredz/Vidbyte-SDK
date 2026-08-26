"""FILE: lint/rules/c001_settings_class_configuration_error_placement.py

PURPOSE:
    Declares C001: a "*Settings" class that is not itself a frozen dataclass
    must not raise ConfigurationError directly in its own methods.
ROLE IN CODEBASE:
    Registered by lint/core/registry.py. Pure-AST rule (ruff_selectors is
    empty); parses files itself via lint/core/parsing.PythonSourceParser.
ARCHITECTURE NOTE:
    Grounded in field-guide/vidbyte-sdk/strict-config-dataclasses.md: "The
    settings class's own __init__ and instance methods contain no raise
    ConfigurationError calls -- every one lives on the dataclass." That
    entry's own cited example, AgentFallbackConfig, no longer exists in this
    codebase (grepped, zero hits; the fallback subsystem was rewritten twice
    since). vidbyte/agents/settings/fallback.py's AgentFallbackSettings is a
    live, current instance of exactly what this rule flags: a plain class
    (not a @dataclass) that raises ConfigurationError directly in five
    methods. PauseDuration in vidbyte/lib/dataclasses/agents.py is a live,
    verified example of the sanctioned shape this rule points readers to.
WHAT NOT TO DO IN THIS FILE:
    Do not widen the class-name heuristic beyond the literal "Settings"
    suffix; vidbyte/lib/registries/*.py legitimately raises
    ConfigurationError from Registry classes, and a name-suffix match keeps
    this rule from flagging that sanctioned, separate use.
RELATED DOCS:
    docs/design/sdk-lint-contract-rules.md
    field-guide/vidbyte-sdk/strict-config-dataclasses.md
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, ClassVar

from lint.core.diagnostic import Finding, RuleDiagnostic
from lint.core.parsing import PythonSourceParser

if TYPE_CHECKING:
    from pathlib import Path

    from lint.core.ruff import RuffFinding

_CONFIGURATION_ERROR_NAME = "ConfigurationError"
_SETTINGS_SUFFIX = "Settings"


class SettingsClassConfigurationErrorPlacementRule:
    """C001: a plain "*Settings" class must delegate validation to a dataclass."""

    rule_id: ClassVar[str] = "C001"
    ruff_selectors: ClassVar[tuple[str, ...]] = ()

    @staticmethod
    def diagnostic() -> RuleDiagnostic:
        # Returns C001's fixed summary/impact/repair/verify-command text.
        return RuleDiagnostic(
            summary=(
                "A class named `*Settings` that is not itself a `@dataclass` raises "
                "`ConfigurationError` directly in one of its own methods. The house pattern "
                "(field-guide/vidbyte-sdk/strict-config-dataclasses.md) is that a settings "
                "class's constructor is a thin adapter over one `@dataclass(frozen=True, "
                "slots=True)` in `vidbyte/lib/dataclasses/`, and every validation rule -- "
                "every `raise ConfigurationError` -- lives on that dataclass's "
                "`__post_init__`, not on the settings class itself."
            ),
            impact=(
                "A dataclass instance is provably valid the moment it is constructed -- no "
                "caller can observe a half-validated object, and nothing downstream needs to "
                "re-check the shape it was handed. Validation scattered across a plain "
                "class's methods does not give that guarantee: a new method can be added "
                "later that skips the check, or two call paths can validate the same field "
                "slightly differently. `vidbyte/agents/settings/fallback.py`'s "
                "`AgentFallbackSettings` is a live example of the debt this creates today: "
                "it raises `ConfigurationError` in five separate methods "
                "(`_validate_models_not_empty`, `_validate_entry_types`, "
                "`_validate_error_types`, `_split_provider_prefix`, `_inherited_provider`) "
                "instead of one dataclass `__post_init__`."
            ),
            repair=(
                "Define a `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/` "
                "whose `__post_init__` owns every one of these checks and raises the same "
                "`ConfigurationError`s. Have the settings class's `__init__` coerce its loose, "
                "ergonomic keyword arguments into one instance of that dataclass, store only "
                "the dataclass instance, and expose the rest as read-only properties reading "
                "from it. `PauseDuration` in `vidbyte/lib/dataclasses/agents.py` is a live, "
                "correct example of this shape: a one-field frozen dataclass whose "
                "`__post_init__` raises `ValueError` for an invalid value. Do not just move the "
                "`raise` statements into `__init__` without a dataclass -- the point is a "
                "provably-valid constructed value, not merely relocating the check."
            ),
            verify_command="python lint/run.py --rule C001",
        )

    @staticmethod
    def find(files: tuple[Path, ...], ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]:
        # Parses every file and flags each ConfigurationError raise inside a plain *Settings class.
        findings: list[Finding] = []
        for path in files:
            module = PythonSourceParser.parse(path)
            if module is None:
                continue
            findings.extend(SettingsClassConfigurationErrorPlacementRule._scan_module(path, module))
        return tuple(findings)

    @staticmethod
    def _scan_module(path: Path, module: ast.Module) -> list[Finding]:
        # Walks every class definition in one module for the flagged pattern.
        findings: list[Finding] = []
        for node in ast.walk(module):
            if isinstance(node, ast.ClassDef) and SettingsClassConfigurationErrorPlacementRule._is_plain_settings_class(node):
                findings.extend(SettingsClassConfigurationErrorPlacementRule._raises_in_class(path, node))
        return findings

    @staticmethod
    def _is_plain_settings_class(class_node: ast.ClassDef) -> bool:
        # True when the class name ends in "Settings" and it carries no @dataclass decorator.
        if not class_node.name.endswith(_SETTINGS_SUFFIX):
            return False
        return not any(SettingsClassConfigurationErrorPlacementRule._is_dataclass_decorator(d) for d in class_node.decorator_list)

    @staticmethod
    def _is_dataclass_decorator(decorator: ast.expr) -> bool:
        # True for bare @dataclass or called @dataclass(...) decorators.
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        return isinstance(target, ast.Name) and target.id == "dataclass"

    @staticmethod
    def _raises_in_class(path: Path, class_node: ast.ClassDef) -> list[Finding]:
        # Finds every `raise ConfigurationError(...)` inside each method, attributed by method name.
        findings: list[Finding] = []
        for member in class_node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                findings.extend(SettingsClassConfigurationErrorPlacementRule._raises_in_method(path, class_node.name, member))
        return findings

    @staticmethod
    def _raises_in_method(path: Path, class_name: str, method_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Finding]:
        # Finds every ConfigurationError raise inside one method's body, however deeply nested.
        findings: list[Finding] = []
        for node in ast.walk(method_node):
            if isinstance(node, ast.Raise) and SettingsClassConfigurationErrorPlacementRule._raises_configuration_error(node):
                findings.append(
                    Finding(
                        rule_id="C001",
                        code="C001",
                        file=path,
                        line=node.lineno,
                        column=node.col_offset,
                        message=(
                            f"{class_name}.{method_node.name} raises ConfigurationError directly; "
                            "move this check to a paired dataclass's __post_init__."
                        ),
                    )
                )
        return findings

    @staticmethod
    def _raises_configuration_error(raise_node: ast.Raise) -> bool:
        # True when the raised exception's callee or bare name is literally "ConfigurationError".
        exc = raise_node.exc
        if exc is None:
            return False
        target = exc.func if isinstance(exc, ast.Call) else exc
        return isinstance(target, ast.Name) and target.id == _CONFIGURATION_ERROR_NAME


__all__ = ["SettingsClassConfigurationErrorPlacementRule"]
