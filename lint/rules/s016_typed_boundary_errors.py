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
    summary = "This rule requires provider, tool, runner, MCP, and CLI boundaries to expose the SDK's typed error hierarchy. It checks raises inside those modules because a builtin exception can escape through a private helper as easily as through a public function. A finding identifies the boundary function and builtin type so the repair can preserve a stable caller-facing failure category. The rule leaves the dedicated error package as the place where typed error classes are defined and organized. The public type should communicate the failure class without forcing every caller to parse implementation-specific text."
    impact = "A builtin exception does not tell an SDK caller whether configuration, provider request, provider response, protocol, or usage state failed. Callers then parse unstable text, catch too broadly, or lose the ability to choose safe retry and remediation behavior. A private parser can also leak a builtin indirectly when its public boundary assumes that internal errors are already translated. The resulting error surface is inconsistent across providers and makes failures harder for agents to classify from one context packet. Inconsistent types also make it difficult to determine which errors are safe to retry and which require configuration or user action."
    repair = "Classify the failure by the boundary it leaves and select the matching type from vidbyte.lib.errors. Translate builtin parsing or validation failures before they cross the provider, tool, runner, MCP, or CLI boundary. Preserve the original cause with from exc when the translation is made in response to a caught exception. Run the focused rule and the affected error-path checks to verify callers receive the stable type without losing useful safe context. Include the error kind and safe diagnostic fields needed by callers while keeping raw provider details out of the public packet."
    examples = (
        "vidbyte/lib/errors/__init__.py - the SDK error hierarchy",
        "vidbyte/lib/http/transport.py - ProviderRequestError at an outbound boundary",
    )
    will_not_work = (
        "Inventing a local RuntimeError subclass outside the canonical error package.",
        "Renaming the helper private while allowing its builtin exception to escape through the public caller.",
    )

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
        return Diagnostic(what_happened=f"Boundary helper {finding.extra.get('function', '<module>')} in {finding.rel_path}:{finding.line} raises builtin {finding.symbol}.", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = TypedBoundaryErrorsRule()
