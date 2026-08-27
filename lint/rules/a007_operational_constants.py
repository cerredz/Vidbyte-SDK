"""FILE: lint/rules/a007_operational_constants.py

PURPOSE: Defines A007 as the SDK's named operational-constant policy.
ROLE IN CODEBASE: Keeps timeout, retry, limit, budget, truncation, and status policy explicit.
ARCHITECTURE NOTE: Detection uses AST parent context and preserves named constants/config values.
FUNCTION INVENTORY: OperationalConstantAnalyzer and OperationalConstantsRule inspect/report.
COMMON MODIFICATION PATTERNS: Change policy vocabulary/exemptions and diagnostics together; rerun A007.
WHAT NOT TO DO: Do not ban ordinary arithmetic, uppercase constants, enums, or config references.
KNOWN EDGE CASES: Zero and one remain findings when they define operational policy.
RELATED DOCS: docs/design/agent-native-lint-rules.md
TESTS: Exercised by python lint/run.py --rule A007.
"""

from __future__ import annotations

import ast
import re

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

OPERATIONAL_TOKENS = (
    "timeout",
    "retry",
    "attempt",
    "backoff",
    "delay",
    "token",
    "char",
    "byte",
    "truncate",
    "limit",
    "budget",
    "status",
    "depth",
    "interval",
)
OPERATIONAL_CALLS = frozenset({"sleep", "urlopen", "send", "request", "read", "read_bytes"})


class OperationalConstantAnalyzer:
    """Finds numeric literals whose surrounding AST names define runtime policy."""

    def analyze(self, source: SourceFile) -> list[tuple[int, str, str]]:
        # Walks numeric literals once and reports only operationally named contexts.
        if source.tree is None:
            return []
        parents = self._parents(source.tree)
        findings: list[tuple[int, str, str]] = []
        for node in ast.walk(source.tree):
            if not self._numeric(node) or self._named_constant(node, parents):
                continue
            context = self._context(node, parents)
            reason = self._reason(context)
            if reason:
                findings.append((node.lineno, str(node.value), reason))
        findings.extend(self._parameter_defaults(source.tree))
        return self._unique(findings)

    def _parents(self, tree: ast.AST) -> dict[ast.AST, ast.AST]:
        # Builds a local parent map so each literal can inspect its semantic context.
        return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}

    def _numeric(self, node: ast.AST) -> bool:
        # Recognizes integer and float constants while excluding boolean sentinels.
        return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)

    def _named_constant(self, node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
        # Allows uppercase assignments that already give the policy a stable name.
        current: ast.AST | None = node
        for _ in range(6):
            if current is None:
                break
            if isinstance(current, (ast.Assign, ast.AnnAssign)):
                targets = current.targets if isinstance(current, ast.Assign) else [current.target]
                names = [target.id for target in targets if isinstance(target, ast.Name)]
                if names and all(self._uppercase(name) for name in names):
                    return True
            current = parents.get(current)
        return False

    def _context(self, node: ast.AST, parents: dict[ast.AST, ast.AST]) -> tuple[ast.AST, ...]:
        # Returns the literal and its bounded enclosing expressions/statements.
        context: list[ast.AST] = [node]
        current = parents.get(node)
        for _ in range(7):
            if current is None:
                break
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                break
            context.append(current)
            current = parents.get(current)
        return tuple(context)

    def _reason(self, context: tuple[ast.AST, ...]) -> str:
        # Explains why a numeric literal is operational based on nearby identifiers.
        names = self._names(context)
        tokens = [token for name in names for token in re.split(r"[_\.]+", name.lower())]
        matched = next((token for token in OPERATIONAL_TOKENS if token in tokens), "")
        if matched:
            return f"operational context contains {matched!r}"
        call_names = {name.lower() for name in names}
        if call_names & OPERATIONAL_CALLS:
            return f"operational call {sorted(call_names & OPERATIONAL_CALLS)[0]!r} receives a literal"
        return ""

    def _names(self, context: tuple[ast.AST, ...]) -> tuple[str, ...]:
        # Collects names, attributes, assignment targets, and keyword labels nearby.
        names: list[str] = []
        for item in context:
            names.extend(node.id for node in ast.walk(item) if isinstance(node, ast.Name))
            names.extend(node.attr for node in ast.walk(item) if isinstance(node, ast.Attribute))
            names.extend(node.arg for node in ast.walk(item) if isinstance(node, ast.keyword) and node.arg)
        return tuple(names)

    def _parameter_defaults(self, tree: ast.Module) -> list[tuple[int, str, str]]:
        # Reports literals in retry/timeout/limit parameter defaults not linked by parents.
        findings: list[tuple[int, str, str]] = []
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            positional = [*function.args.posonlyargs, *function.args.args]
            defaults = [*([None] * (len(positional) - len(function.args.defaults))), *function.args.defaults]
            keyword = list(zip(function.args.kwonlyargs, function.args.kw_defaults, strict=True))
            pairs = [(parameter, default) for parameter, default in zip(positional, defaults, strict=True) if default is not None] + [(parameter, default) for parameter, default in keyword if default is not None]
            for parameter, default in pairs:
                if not self._operational_name(parameter.arg):
                    continue
                for node in ast.walk(default):
                    if self._numeric(node):
                        findings.append((node.lineno, str(node.value), f"parameter default {parameter.arg!r} is operational"))
        return findings

    def _operational_name(self, name: str) -> bool:
        # Matches a parameter name containing one of the documented policy tokens.
        return any(token in re.split(r"[_\.]+", name.lower()) for token in OPERATIONAL_TOKENS)

    def _uppercase(self, name: str) -> bool:
        # Identifies conventional module/class constants while allowing private prefixes.
        return name.lstrip("_").isupper()

    def _unique(self, findings: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
        # De-duplicates parent-context and parameter-default reports for one literal.
        return list(dict.fromkeys(findings))


class OperationalConstantsRule(Rule):
    """Requires runtime policy values to have named ownership."""

    id = "A007"
    name = "operational-constants"
    severity = "blocking"
    summary = "Operational numeric policy values come from named constants, enums, or configuration."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans tracked production modules and preserves literal-level locations.
        findings: list[Finding] = []
        analyzer = OperationalConstantAnalyzer()
        for source in catalog.python_files():
            for line, literal, reason in analyzer.analyze(source):
                findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=literal, extra={"literal": literal, "reason": reason}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Connects an unexplained number to the named-policy repair expected by agents.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} uses operational literal {finding.symbol}: {finding.extra.get('reason', 'policy value')}.", why_blocked="A number such as 30, 500, or 429 has no durable meaning at its use site. Agents cannot tell whether changing it affects timeout safety, retries, context capacity, truncation, billing budget, or provider behavior, so a local edit can violate a cross-cutting contract.", how_to_fix="Move the policy value to a nearby uppercase named constant, enum, or typed configuration object with a meaningful name and documentation. Pass that name through the call or comparison so the owner and intended unit remain visible.", correct_examples=("vidbyte/tools/builtins/operations/clients/_base.py - RetryPolicy and named response/date limits own operational values.", "vidbyte/lib/dataclasses/config.py - typed configuration constants define bounded prompt/runtime policy."), will_not_work=("Renaming the local variable while leaving a numeric literal at the boundary.", "Adding a comment after the number but keeping duplicate literals in callers or raising a lint baseline."), verify=self.verify_command())


RULE = OperationalConstantsRule()
