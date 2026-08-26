"""FILE: lint/rules/c002_duplicate_inline_bool_guard_validation.py

PURPOSE:
    Declares C002: the same meaningful parameter name validated with the
    `isinstance(<name>, bool)` idiom in two or more distinct functions
    should be centralized into one dataclass instead of copied inline.
ROLE IN CODEBASE:
    Registered by lint/core/registry.py. Pure-AST rule (ruff_selectors is
    empty); parses files itself via lint/core/parsing.PythonSourceParser.
ARCHITECTURE NOTE:
    Grounded in field-guide/vidbyte-sdk/strict-config-dataclasses.md's
    second entry: "grep the parameter name for repeated isinstance(...,
    bool) / range checks across files." Verified against the live tree:
    `timeout_seconds` appears in this exact idiom in both
    vidbyte/workflows/validation.py and vidbyte/workflows/contracts.py;
    `max_trace_iterations` appears in both
    vidbyte/lib/dataclasses/continual_trace_descriptor.py and
    vidbyte/lib/dataclasses/trace.py. Roughly 60 raw isinstance(x, bool)
    hits exist repo-wide, but most use generic identifiers (value, raw,
    data) validating unrelated fields -- matching on those would be pure
    noise, so _GENERIC_IDENTITIES excludes them by design. That is a
    precision/recall tradeoff stated here explicitly, not hidden: a real
    duplicate using one of these generic names is a false negative this
    rule accepts in exchange for not drowning every run in unrelated noise.
WHAT NOT TO DO IN THIS FILE:
    Do not add more names to _GENERIC_IDENTITIES without re-checking the
    repo-wide grep; the list is deliberately short and evidence-based.
RELATED DOCS:
    docs/design/sdk-lint-contract-rules.md
    field-guide/vidbyte-sdk/strict-config-dataclasses.md
"""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar

from lint.core.diagnostic import Finding, RuleDiagnostic
from lint.core.parsing import PythonSourceParser

if TYPE_CHECKING:
    from pathlib import Path

    from lint.core.ruff import RuffFinding

_GENERIC_IDENTITIES = frozenset({"value", "raw", "data", "entry", "item", "obj", "setting", "x", "v", "val", "flag"})


class _Occurrence:
    """One isinstance(<name>, bool) sighting: where, and in which function."""

    __slots__ = ("identity", "path", "qualname", "line", "column")

    def __init__(self, identity: str, path: Path, qualname: str, line: int, column: int) -> None:
        # Records one sighting's identity, location, and enclosing function name.
        self.identity = identity
        self.path = path
        self.qualname = qualname
        self.line = line
        self.column = column


class DuplicateInlineBoolGuardValidationRule:
    """C002: the same named parameter validated inline in 2+ distinct functions."""

    rule_id: ClassVar[str] = "C002"
    ruff_selectors: ClassVar[tuple[str, ...]] = ()

    @staticmethod
    def diagnostic() -> RuleDiagnostic:
        # Returns C002's fixed summary/impact/repair/verify-command text.
        return RuleDiagnostic(
            summary=(
                "The same meaningful parameter or attribute name is validated with the "
                "`isinstance(<name>, bool)` idiom -- the house pattern for rejecting a bool "
                "masquerading as an int -- in two or more distinct functions. Real, current "
                "examples: `timeout_seconds` in both `vidbyte/workflows/validation.py` and "
                "`vidbyte/workflows/contracts.py`; `max_trace_iterations` in both "
                "`vidbyte/lib/dataclasses/continual_trace_descriptor.py` and "
                "`vidbyte/lib/dataclasses/trace.py`."
            ),
            impact=(
                "Two independent inline copies of the same validation rule drift silently: "
                "one call site gets a bugfix, a widened range, or an extra check, and the "
                "other does not, so the same-named value is 'valid' in one place and not "
                "the other with no compiler or reviewer able to see the mismatch from either "
                "site alone."
            ),
            repair=(
                "Define one `@dataclass(frozen=True, slots=True)` in `vidbyte/lib/dataclasses/` "
                "whose `__post_init__` owns this exact check, then have every flagged call site "
                "construct that dataclass instead of repeating the inline `isinstance` guard. "
                "`PauseDuration` in `vidbyte/lib/dataclasses/agents.py` is the existing template "
                "for a single-field validated dataclass of this shape. This rule intentionally "
                "does not fire on generic single-word names (`value`, `raw`, `data`, and "
                "similar) because those validate unrelated fields at each site; it only flags "
                "specific, meaningful names, so every finding names a real, checkable "
                "duplication, not a coincidence of naming."
            ),
            verify_command="python lint/run.py --rule C002",
        )

    @staticmethod
    def find(files: tuple[Path, ...], ruff_findings: tuple[RuffFinding, ...]) -> tuple[Finding, ...]:
        # Collects every occurrence, groups by identity, and flags identities with 2+ occurrences.
        occurrences = DuplicateInlineBoolGuardValidationRule._collect_occurrences(files)
        by_identity: dict[str, list[_Occurrence]] = defaultdict(list)
        for occurrence in occurrences:
            by_identity[occurrence.identity].append(occurrence)
        findings: list[Finding] = []
        for identity, group in sorted(by_identity.items()):
            # Each occurrence already comes from one distinct FunctionDef (see
            # _occurrences_in_function's per-function dedup), so group length alone is the
            # true distinct-occurrence count -- do not dedupe by (path, qualname) here, since
            # two different classes in the same file can share a method name like __post_init__.
            if len(group) < 2:
                continue
            findings.extend(DuplicateInlineBoolGuardValidationRule._findings_for_group(identity, group))
        return tuple(findings)

    @staticmethod
    def _collect_occurrences(files: tuple[Path, ...]) -> list[_Occurrence]:
        # Parses every file and walks every function for the isinstance(<name>, bool) idiom.
        occurrences: list[_Occurrence] = []
        for path in files:
            module = PythonSourceParser.parse(path)
            if module is None:
                continue
            for func in ast.walk(module):
                if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    occurrences.extend(DuplicateInlineBoolGuardValidationRule._occurrences_in_function(path, func))
        return occurrences

    @staticmethod
    def _occurrences_in_function(path: Path, func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[_Occurrence]:
        # Finds every isinstance(<name>, bool) call directly inside one function's body.
        found: list[_Occurrence] = []
        seen_identities: set[str] = set()
        for node in ast.walk(func):
            identity = DuplicateInlineBoolGuardValidationRule._bool_guard_identity(node)
            if identity is None or identity in _GENERIC_IDENTITIES or identity in seen_identities:
                continue
            seen_identities.add(identity)
            found.append(_Occurrence(identity=identity, path=path, qualname=func.name, line=node.lineno, column=node.col_offset))
        return found

    @staticmethod
    def _bool_guard_identity(node: ast.AST) -> str | None:
        # Returns the validated name's identity when node is isinstance(<name-or-attr>, bool).
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "isinstance"):
            return None
        if len(node.args) != 2 or not (isinstance(node.args[1], ast.Name) and node.args[1].id == "bool"):
            return None
        target = node.args[0]
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Attribute):
            return target.attr
        return None

    @staticmethod
    def _findings_for_group(identity: str, group: list[_Occurrence]) -> list[Finding]:
        # Emits one Finding per occurrence, each naming every other site sharing the identity.
        findings: list[Finding] = []
        for occurrence in group:
            others = sorted(f"{o.path}:{o.line} ({o.qualname})" for o in group if o is not occurrence)
            findings.append(
                Finding(
                    rule_id="C002",
                    code="C002",
                    file=occurrence.path,
                    line=occurrence.line,
                    column=occurrence.column,
                    message=f"'{identity}' is validated with isinstance(..., bool) here and also in: {', '.join(others)}.",
                )
            )
        return findings


__all__ = ["DuplicateInlineBoolGuardValidationRule"]
