"""FILE: lint/rules/s013_bounded_untrusted_responses.py

PURPOSE: Requires byte ceilings where tools ingest untrusted external content.
ROLE IN CODEBASE: Prevents searches/fetches/MCP responses from exhausting process memory.
ARCHITECTURE NOTE: Provider model JSON is ratcheted separately from ingestion tools.
FUNCTION INVENTORY: ResponseCeilingVisitor checks transport calls in scoped paths.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md
TESTS: Exercised by python lint/run.py --rule S013.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

SCOPED_PREFIXES = ("vidbyte/tools/builtins/code_search/", "vidbyte/tools/builtins/mcp/", "vidbyte/tools/builtins/operations/", "vidbyte/tools/mcp/")
REQUEST_METHODS = frozenset({"request", "request_bytes", "stream_request"})


class ResponseCeilingVisitor(ast.NodeVisitor):
    """Collects untrusted transport calls without a visible response byte ceiling."""

    def __init__(self) -> None:
        # Starts an empty call/method fact list.
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Requires max_response_bytes on ingestion-boundary transport calls.
        method = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if method in REQUEST_METHODS and not any(keyword.arg == "max_response_bytes" for keyword in node.keywords):
            self.hits.append((node.lineno, method))
        self.generic_visit(node)


class BoundedUntrustedResponsesRule(Rule):
    """Requires external content ingestion to declare a maximum response size."""

    id = "S013"
    name = "bounded-untrusted-responses"
    severity = "blocking"
    summary = "Search, fetch, code-search, and MCP response bodies have byte ceilings."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans only paths that ingest externally controlled content into agent context.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not source.rel.startswith(SCOPED_PREFIXES):
                continue
            visitor = ResponseCeilingVisitor()
            visitor.visit(source.tree)
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=method, extra={"method": method}) for line, method in visitor.hits)
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Directs the boundary to streaming/bounded transport behavior.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} ingests an untrusted {finding.symbol} response without max_response_bytes.", why_blocked="A remote endpoint controls body size; buffering it whole can exhaust memory and inject unbounded content into an agent context before parsing or truncation runs.", how_to_fix="Pass a named/configured max_response_bytes ceiling to HttpTransport and keep its bounded streaming implementation. For sync/MCP transports, add an equivalent bounded-read parameter to the owning transport before calling it here.", correct_examples=("vidbyte/lib/http/transport.py - _send_bounded streams and enforces the ceiling",), will_not_work=("Truncating decoded text after the entire body has already been read.", "Checking only Content-Length; chunked responses may omit or lie about it."), verify=self.verify_command())


RULE = BoundedUntrustedResponsesRule()
