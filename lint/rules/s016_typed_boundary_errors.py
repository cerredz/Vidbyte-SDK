"""FILE: lint/rules/s016_typed_boundary_errors.py

PURPOSE: Requires typed SDK errors where failures leave provider/tool/runner boundaries.
ROLE IN CODEBASE: Gives callers stable kinds, fields, and handling semantics.
ARCHITECTURE NOTE: Boundary modules translate builtins locally before they escape.
FUNCTION INVENTORY: BoundaryErrorVisitor tracks nearest public function and builtin raises.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md
TESTS: Exercised by python lint/run.py --rule S016.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

BOUNDARY_PREFIXES = ("vidbyte/providers/", "vidbyte/tools/mcp/", "vidbyte/tools/builtins/", "vidbyte/lib/runners/", "vidbyte/cli/")
EXEMPT_PREFIXES = ("vidbyte/lib/errors/",)
BUILTINS = frozenset({"Exception", "RuntimeError", "TypeError", "ValueError"})


class BoundaryErrorVisitor(ast.NodeVisitor):
    """Collects builtin raises inside modules that own external boundaries."""

    def __init__(self) -> None:
        # Starts an empty function stack and raise fact list.
        self.functions: list[str] = []
        self.hits: list[tuple[int, str, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Tracks sync callable visibility while scanning its body.
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # Tracks async callable visibility with identical rules.
        self.visit_FunctionDef(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        # Records direct builtin construction anywhere inside a scoped boundary module.
        function = self.functions[-1] if self.functions else "<module>"
        raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        name = raised.id if isinstance(raised, ast.Name) else ""
        if name in BUILTINS:
            self.hits.append((node.lineno, function, name))
        self.generic_visit(node)


class TypedBoundaryErrorsRule(Rule):
    """Requires external-boundary modules to raise vidbyte.lib.errors types."""

    id = "S016"
    name = "typed-boundary-errors"
    severity = "blocking"
    summary = "Provider, tool, runner, MCP, and CLI boundaries translate builtin failures."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans declared boundary packages so private helpers cannot leak builtins indirectly.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not source.rel.startswith(BOUNDARY_PREFIXES) or source.rel.startswith(EXEMPT_PREFIXES):
                continue
            visitor = BoundaryErrorVisitor()
            visitor.visit(source.tree)
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=error, extra={"function": function, "error": error}) for line, function, error in visitor.hits)
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Routes one builtin failure to the SDK's stable typed error hierarchy.
        return Diagnostic(what_happened=f"Boundary helper {finding.extra.get('function', '<module>')} in {finding.rel_path}:{finding.line} raises builtin {finding.symbol}.", why_blocked="Users cannot distinguish configuration, provider request, provider response, protocol, and usage failures without parsing message text. A private helper's builtin still escapes unless translated at that exact module boundary.", how_to_fix="Raise the matching class from vidbyte.lib.errors and preserve a caught cause with from exc. If a parser must use a builtin internally, catch and translate it before control can leave the boundary module.", correct_examples=("vidbyte/lib/errors/__init__.py - SDK error hierarchy", "vidbyte/lib/http/transport.py - ProviderRequestError translation"), will_not_work=("Inventing a local RuntimeError subclass outside the error package.", "Renaming the helper private while the builtin still escapes through its caller."), verify=self.verify_command())


RULE = TypedBoundaryErrorsRule()
