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
    summary = "Every outbound HTTP/transport request declares a timeout."

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
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} calls outbound method {finding.symbol} without an explicit timeout keyword.", why_blocked="An agent run can remain occupied forever by a stalled provider, search API, upload, or stream. Hidden library defaults also drift by transport and version.", how_to_fix="Pass timeout_seconds=config.timeout_seconds to SDK transports or timeout=<bounded value/config> to an adapter leaf. The value must come from typed configuration or a named module constant.", correct_examples=("vidbyte/providers/openai.py - provider calls pass config.timeout_seconds",), will_not_work=("Relying on the transport method's default or an undocumented third-party default.", "Adding an arbitrarily huge timeout at the call site."), verify=self.verify_command())


RULE = ExplicitOutboundTimeoutRule()
