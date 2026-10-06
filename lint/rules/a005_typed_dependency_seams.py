"""FILE: lint/rules/a005_typed_dependency_seams.py

PURPOSE: Defines A005 as the SDK's typed injected-dependency seam policy.
ROLE IN CODEBASE: Keeps transport, runner, store, client, tracer, and fetcher capabilities inspectable.
ARCHITECTURE NOTE: Detection examines annotations structurally and never imports dependency types.
FUNCTION INVENTORY: DependencySeamAnalyzer and TypedDependencySeamsRule inspect/report.
COMMON MODIFICATION PATTERNS: Change dependency names/exemptions and diagnostics together; rerun A005.
WHAT NOT TO DO: Do not ban wire-format Any, infer runtime protocols, or accept opaque object seams.
KNOWN EDGE CASES: Mapping/sequence payload parameters remain wire-format exemptions.
RELATED DOCS: docs/design/agent-native-lint-rules.md
TESTS: Exercised by python lint/run.py --rule A005.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

DEPENDENCY_TOKENS = ("transport", "runner", "store", "client", "tracer", "fetcher")
WIRE_FORMAT_NAMES = frozenset({"payload", "json_body", "headers", "metadata", "options", "data"})
WIRE_CONTAINER_NAMES = frozenset({"Mapping", "MutableMapping", "dict", "Sequence", "list", "tuple"})


class DependencySeamAnalyzer:
    """Finds opaque annotations on named infrastructure dependencies."""

    def analyze(self, source: SourceFile) -> list[tuple[int, str, str, str]]:
        # Walks functions and returns one finding per dependency parameter annotation.
        if source.tree is None:
            return []
        findings: list[tuple[int, str, str, str]] = []
        for node in ast.walk(source.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for parameter in self._parameters(node):
                if self._dependency_name(parameter.arg) and self._opaque(parameter.annotation) and not self._wire_format(parameter):
                    annotation = ast.unparse(parameter.annotation) if parameter.annotation is not None else "<missing>"
                    findings.append((parameter.lineno, node.name, parameter.arg, annotation))
        return findings

    def _parameters(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[ast.arg, ...]:
        # Returns all ordinary and keyword-only parameters while ignoring variadic bags.
        return (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)

    def _dependency_name(self, name: str) -> bool:
        # Matches explicit infrastructure seam names without requiring a naming style change.
        normalized = name.lstrip("_").lower()
        return normalized in DEPENDENCY_TOKENS

    def _opaque(self, annotation: ast.expr | None) -> bool:
        # Flags exact object annotations and any annotation containing unconstrained Any.
        if annotation is None:
            return False
        names = {node.id for node in ast.walk(annotation) if isinstance(node, ast.Name)}
        attributes = {node.attr for node in ast.walk(annotation) if isinstance(node, ast.Attribute)}
        return "object" in names or "object" in attributes or "Any" in names or "Any" in attributes

    def _wire_format(self, parameter: ast.arg) -> bool:
        # Allows Any inside named mapping/sequence payloads but not dependency seams.
        if parameter.arg not in WIRE_FORMAT_NAMES or parameter.annotation is None:
            return False
        root = parameter.annotation
        if isinstance(root, ast.Subscript):
            root = root.value
        name = root.id if isinstance(root, ast.Name) else root.attr if isinstance(root, ast.Attribute) else ""
        return name in WIRE_CONTAINER_NAMES


class TypedDependencySeamsRule(Rule):
    """Requires injected infrastructure to use concrete interfaces or Protocols."""

    id = "A005"
    name = "typed-dependency-seams"
    severity = "blocking"
    summary = "Injected infrastructure dependencies cannot collapse to object or unconstrained Any."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans tracked production functions and preserves parameter-level locations.
        findings: list[Finding] = []
        analyzer = DependencySeamAnalyzer()
        for source in catalog.python_files():
            for line, function, parameter, annotation in analyzer.analyze(source):
                findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=f"{function}.{parameter}", extra={"parameter": parameter, "annotation": annotation}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Directs the repair toward a capability-specific interface rather than a cast.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} dependency {finding.symbol} is annotated as {finding.extra.get('annotation', 'object/Any')}.", why_blocked="An opaque seam hides the methods and lifecycle a transport, runner, store, tracer, client, or fetcher must provide. Agents then infer capabilities from call sites and can wire an incompatible implementation that fails late or bypasses the intended boundary.", how_to_fix="Define or reuse a narrow concrete interface or `Protocol` containing the operations this function actually calls, then annotate the injected parameter with that type. Keep `Any` confined to explicitly named wire-format mappings such as payload or metadata values.", correct_examples=("vidbyte/tools/builtins/operations/clients/_base.py - transport is typed as HttpTransport.", "vidbyte/tools/builtins/code_search/semantic.py - EmbeddingProvider is a capability-specific Protocol."), will_not_work=("Replacing object with Any, adding a cast, or hiding the dependency behind a dictionary.", "Treating Mapping[str, Any] as a valid annotation for an injected store or client."), verify=self.verify_command())


RULE = TypedDependencySeamsRule()
