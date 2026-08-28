"""FILE: lint/rules/s011_raw_http_client_ownership.py

PURPOSE: Keeps raw HTTP libraries inside the SDK's transport adapters.
ROLE IN CODEBASE: Centralizes retries, errors, timeouts, limits, and test injection.
ARCHITECTURE NOTE: urllib.parse is not an HTTP client and remains allowed.
FUNCTION INVENTORY: RawHttpImportVisitor resolves imports of owned client modules.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md
TESTS: Exercised by python lint/run.py --rule S011.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

OWNED_MODULES = ("http.client", "httpx", "requests", "urllib.request")
SANCTIONED_FILES = frozenset({"vidbyte/lib/http/transport.py", "vidbyte/tools/mcp/transport.py"})


class RawHttpImportVisitor(ast.NodeVisitor):
    """Collects imports that transfer raw HTTP ownership outside adapters."""

    def __init__(self) -> None:
        # Starts an empty import fact list.
        self.hits: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        # Records direct owned-module imports and submodules.
        self.hits.extend((node.lineno, alias.name) for alias in node.names if alias.name in OWNED_MODULES or alias.name.startswith(tuple(f"{name}." for name in OWNED_MODULES)))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Records from-imports only when the imported module owns HTTP I/O.
        if node.module and (node.module in OWNED_MODULES or node.module.startswith(tuple(f"{name}." for name in OWNED_MODULES))):
            self.hits.append((node.lineno, node.module))
        if node.module in {"http", "urllib"} and any(alias.name in {"client", "request"} for alias in node.names):
            self.hits.append((node.lineno, f"{node.module}.{'client' if node.module == 'http' else 'request'}"))


class RawHttpClientOwnershipRule(Rule):
    """Requires production HTTP behavior to go through designated transport adapters."""

    id = "S011"
    name = "raw-http-client-ownership"
    severity = "blocking"
    summary = "Raw httpx/requests/urllib clients live only in transport adapter modules."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans all production modules except the two explicit transport owners.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or source.rel in SANCTIONED_FILES:
                continue
            visitor = RawHttpImportVisitor()
            visitor.visit(source.tree)
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=module, extra={"module": module}) for line, module in visitor.hits)
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Routes a raw client import to the shared injected transport contract.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} imports raw HTTP client module {finding.extra.get('module', finding.symbol)} outside a transport adapter.", why_blocked="A second HTTP stack chooses its own timeout, retry, response-size, error, redaction, and test-injection behavior, so providers no longer share one reliable boundary.", how_to_fix="Add the needed method to HttpTransport or SyncHttpTransport in vidbyte/lib/http/transport.py, then inject and call that transport here. MCP protocol-specific transport behavior remains in vidbyte/tools/mcp/transport.py.", correct_examples=("vidbyte/lib/http/transport.py - canonical async/sync HTTP ownership",), will_not_work=("Wrapping the raw call in a local helper or aliasing the import.", "Adding another allowlisted provider module; providers consume transports rather than own clients."), verify=self.verify_command())


RULE = RawHttpClientOwnershipRule()
