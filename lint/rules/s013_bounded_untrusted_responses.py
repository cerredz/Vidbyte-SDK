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
    summary = "This rule requires every untrusted ingestion boundary to declare a maximum response size. It covers search, fetch, browser, code-search, and MCP content before that content becomes an in-memory SDK result or agent context. A finding identifies a remote body that can be read without a transport-enforced byte ceiling or bounded streaming path. The rule keeps resource protection at the boundary where the remote party still controls the amount of data received. The byte budget is part of the operation contract and must apply before full buffering or downstream parsing."
    impact = "A remote endpoint controls response size and can send much more data than the operation's normal result requires. Reading that body in full can exhaust process memory, delay an agent run, or inject an unbounded amount of untrusted text into later reasoning. Post-read truncation does not prevent the allocation or the network cost, and Content-Length cannot be trusted for every transfer mode. The missing ceiling therefore creates a denial-of-service and context-integrity risk at a high-leverage boundary. A limit applied only after decoding also leaves parsers, logs, and token budgets exposed to the oversized body."
    repair = "Identify the untrusted response boundary and choose the maximum byte budget from the operation's typed policy or named configuration. Pass max_response_bytes to the owning HTTP transport and keep enforcement in its bounded streaming or read helper. For synchronous or MCP transports, add the equivalent bounded-read capability to the adapter before changing the caller. Run the focused rule and a response-size failure check that proves oversized chunked and ordinary responses stop before full buffering. Confirm the failure is translated into the SDK's safe error contract and that the accepted boundary still preserves complete normal responses."
    examples = (
        "vidbyte/lib/http/transport.py - _send_bounded enforces the response ceiling while reading",
        "A search or fetch call that passes a configured max_response_bytes value",
    )
    will_not_work = (
        "Truncating decoded text after the entire remote body has already been read.",
        "Checking only Content-Length while allowing chunked responses to bypass the byte budget.",
    )

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
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} ingests an untrusted {finding.symbol} response without max_response_bytes.", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = BoundedUntrustedResponsesRule()
