"""FILE: lint/rules/s017_no_raw_exception_disclosure.py

PURPOSE: Prevents caught exception strings from becoming public SDK result/error text.
ROLE IN CODEBASE: Keeps filesystem paths, secrets, payloads, and provider internals private.
ARCHITECTURE NOTE: Structured internal logging remains allowed and is not scanned here.
FUNCTION INVENTORY: RawExceptionDisclosureVisitor tracks handler names and public constructors.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md
TESTS: Exercised by python lint/run.py --rule S017.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

SCOPED_PREFIXES = ("vidbyte/providers/", "vidbyte/tools/", "vidbyte/mcp_server/", "vidbyte/lib/runners/")


class RawExceptionDisclosureVisitor(ast.NodeVisitor):
    """Collects raw caught-exception interpolation outside structured logging calls."""

    def __init__(self) -> None:
        # Starts an empty caught-name stack and disclosure fact list.
        self.caught: list[set[str]] = []
        self.hits: list[tuple[int, str, str]] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # Limits exception-name tracking to the lexical handler body.
        self.caught.append({node.name} if node.name else set())
        for statement in node.body:
            self.visit(statement)
        self.caught.pop()

    def visit_Call(self, node: ast.Call) -> None:
        # Flags raw conversion/interpolation passed to non-logging constructors/calls.
        names = set().union(*self.caught) if self.caught else set()
        if names and self._is_public_sink(node) and not self._is_logging(node):
            self._record_raw(node, names)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        # Treats a raw caught exception returned from a handler as public disclosure.
        names = set().union(*self.caught) if self.caught else set()
        if names and node.value is not None:
            self._record_raw(node.value, names)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Tracks raw exception text persisted on public-facing error/message attributes.
        names = set().union(*self.caught) if self.caught else set()
        public_target = any(isinstance(target, ast.Attribute) and any(term in target.attr.lower() for term in ("error", "message")) for target in node.targets)
        if names and public_target:
            self._record_raw(node.value, names)
        self.generic_visit(node)

    def _record_raw(self, node: ast.AST, names: set[str]) -> None:
        # Records conversions and f-string interpolation of active caught names.
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id in {"str", "repr"} and child.args and isinstance(child.args[0], ast.Name) and child.args[0].id in names:
                self.hits.append((child.lineno, child.args[0].id, "raw exception conversion"))
            if isinstance(child, ast.JoinedStr):
                exposed = [part.value.id for part in child.values if isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name) and part.value.id in names]
                self.hits.extend((child.lineno, name, "raw exception interpolation") for name in exposed)

    @staticmethod
    def _is_public_sink(node: ast.Call) -> bool:
        # Recognizes stable error/result constructors rather than every internal helper call.
        if isinstance(node.func, ast.Name):
            return node.func.id.endswith("Error")
        if isinstance(node.func, ast.Attribute):
            return node.func.attr in {"error", "_failed_result"} or node.func.attr.endswith("error")
        return False

    @staticmethod
    def _is_logging(node: ast.Call) -> bool:
        # Recognizes internal logger/logging calls as operator-only diagnostics.
        return isinstance(node.func, ast.Attribute) and any(term in ast.unparse(node.func.value).lower() for term in ("logger", "logging"))


class NoRawExceptionDisclosureRule(Rule):
    """Requires stable redacted public errors instead of raw exception text."""

    id = "S017"
    name = "no-raw-exception-disclosure"
    severity = "blocking"
    summary = (
        "This rule prevents caught exception objects from becoming unfiltered public SDK text. "
        "It covers provider, tool, MCP, runner, and result boundaries where third-party messages may contain secrets or unstable implementation detail. "
        "A finding identifies the conversion or interpolation that can move raw exception content into a caller-visible result or error. "
        "The rule permits structured internal logging while requiring the public surface to use stable and deliberately redacted data."
    )
    impact = (
        "Raw third-party exception text can contain request URLs, local paths, credentials, response bodies, headers, or provider internals. "
        "Echoing it makes the SDK's public contract change whenever a dependency changes its wording or diagnostic payload. "
        "It can also disclose sensitive data to an agent or user who only needs a safe error category and remediation path. "
        "The violation therefore combines information disclosure, contract instability, and noisy failure handling."
    )
    repair = (
        "Separate the stable public error kind and safe message from the internal exception object at the boundary. "
        "Use an existing sanitizer to produce a bounded redacted excerpt only when operators genuinely need provider detail. "
        "Keep the raw exception in structured internal logging or as a chained cause, and never interpolate it into ToolResult, public error, or user-facing message fields. "
        "Run the focused rule and a secret-bearing failure check that asserts both useful public context and absence of the original sensitive text."
    )
    examples = (
        "vidbyte/tools/builtins/operations/base.py - stable operation error metadata",
        "An internal structured log carrying redacted detail while the public result carries only a safe error kind",
    )
    will_not_work = (
        "Truncating str(exc) without first applying an explicit redaction policy.",
        "Renaming the caught variable or routing it through an f-string helper before returning it publicly.",
    )

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans external-facing packages where returned/raised text reaches SDK users.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not source.rel.startswith(SCOPED_PREFIXES):
                continue
            visitor = RawExceptionDisclosureVisitor()
            visitor.visit(source.tree)
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=name, extra={"reason": reason}) for line, name, reason in visitor.hits)
        return list({(item.rel_path, item.line, item.symbol): item for item in findings}.values())

    def explain(self, finding: Finding) -> Diagnostic:
        # Separates stable public metadata from bounded/redacted internal detail.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} exposes caught exception {finding.symbol} through {finding.extra.get('reason', 'public text')}.", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = NoRawExceptionDisclosureRule()
