"""FILE: lint/rules/s012_explicit_outbound_timeout.py

PURPOSE: Requires every outbound request call to declare its timeout policy.
ROLE IN CODEBASE: Prevents provider/tool calls from hanging agent execution indefinitely.
ARCHITECTURE NOTE: Transport private leaves receiving required timeout parameters are allowed.
FUNCTION INVENTORY: OutboundTimeoutVisitor inspects known request methods and keywords.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md
TESTS: Exercised by python lint/run.py --rule S012.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

REQUEST_METHODS = frozenset({"request", "request_bytes", "stream_request", "upload_multipart", "urlopen"})
TIMEOUT_KEYWORDS = frozenset({"timeout", "timeout_seconds"})
CONSTRUCTOR_TIMEOUT_FILES = frozenset({"vidbyte/tools/mcp/client.py"})


class OutboundTimeoutVisitor(ast.NodeVisitor):
    """Collects known outbound calls without explicit timeout keywords."""

    def __init__(self) -> None:
        # Starts an empty call/method fact list.
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Records request methods only when no timeout keyword is present.
        method = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
        if method in REQUEST_METHODS and not any(keyword.arg in TIMEOUT_KEYWORDS for keyword in node.keywords):
            self.hits.append((node.lineno, method))
        self.generic_visit(node)


class ExplicitOutboundTimeoutRule(Rule):
    """Requires call-site-visible timeout decisions for outbound I/O."""

    id = "S012"
    name = "explicit-outbound-timeout"
    severity = "blocking"
    summary = "This rule requires every outbound HTTP or transport request to expose an intentional timeout decision. It covers provider requests, search and fetch operations, uploads, streams, and other calls that can hold an agent run open. A finding marks a boundary where the timeout is hidden in a library default or omitted from the call's visible contract. The rule keeps liveness policy close enough to the caller that a maintainer can audit and tune it without guessing. Explicit timeout ownership also makes cancellation and retry behavior reviewable at the same boundary."
    impact = "A request without an explicit timeout can occupy an agent worker indefinitely when a provider, network, or stream stalls. Hidden defaults vary by transport library and version, so the same operation can have inconsistent liveness across environments. An indefinitely blocked call also delays cancellation, retries, resource cleanup, and the final response shown to the user. The missing timeout is therefore a reliability and capacity defect rather than a minor configuration omission. In a multi-request run, one unbounded call can consume the capacity needed to complete otherwise healthy work."
    repair = "Find the typed timeout policy for the operation before selecting a value at the call site. Pass config.timeout_seconds to SDK transports or pass a bounded timeout value to a raw-client adapter leaf that owns the request. Keep the timeout explicit for streams and uploads as well as ordinary requests, and do not replace a missing policy with an arbitrarily huge constant. Run the focused rule plus timeout, cancellation, and retry checks that exercise the affected outbound boundary. Verify both the normal request and the stall path so the value is actually enforced by the transport rather than merely stored in configuration."
    examples = (
        "vidbyte/providers/openai.py - provider calls pass the configured timeout",
        "A transport leaf receiving a required timeout value from its public owner",
    )
    will_not_work = (
        "Relying on the transport method's default or an undocumented third-party library default.",
        "Adding an arbitrarily large timeout at the call site without tying it to typed configuration or lifecycle policy.",
    )

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans production calls while excluding the private transport leaves they feed.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or source.rel in CONSTRUCTOR_TIMEOUT_FILES:
                continue
            visitor = OutboundTimeoutVisitor()
            visitor.visit(source.tree)
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=method, extra={"method": method}) for line, method in visitor.hits)
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Requires the timeout to originate in typed caller configuration.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} calls outbound method {finding.symbol} without an explicit timeout keyword.", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = ExplicitOutboundTimeoutRule()
