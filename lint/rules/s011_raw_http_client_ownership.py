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
    summary = (
        "This rule establishes one ownership boundary for raw HTTP clients used by the SDK. "
        "It keeps provider, search, upload, retry, timeout, response-limit, and error behavior behind the designated transport adapters. "
        "A finding identifies a module that has taken direct ownership of an HTTP library instead of consuming the injected SDK transport contract. "
        "The boundary is intentionally narrow so protocol-specific MCP transport code remains distinguishable from general provider HTTP behavior."
    )
    impact = (
        "A second HTTP stack can silently choose different timeout, retry, response-size, exception, redaction, and test-injection behavior. "
        "That divergence means two providers may handle the same network failure differently even though callers expect one SDK contract. "
        "It also makes security and resource limits dependent on which module authors happened to import a client. "
        "The defect therefore expands operational behavior without a single place where maintainers can audit or repair it."
    )
    repair = (
        "Identify the transport capability the module needs and add or reuse that capability on the owning adapter. "
        "Inject HttpTransport or SyncHttpTransport through the existing constructor or protocol instead of importing a raw client locally. "
        "Keep raw client construction, retries, limits, and exception translation inside the designated adapter, with MCP-specific behavior in its sanctioned transport file. "
        "Run the focused rule and the relevant provider or tool checks after confirming the new call preserves timeout and error semantics."
    )
    examples = (
        "vidbyte/lib/http/transport.py - canonical ownership for general HTTP clients",
        "vidbyte/tools/mcp/transport.py - the dedicated protocol-specific transport adapter",
    )
    will_not_work = (
        "Wrapping the raw call in a local helper or aliasing the imported client.",
        "Adding another provider to the allowlist when the provider should consume an existing transport capability.",
    )

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
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} imports raw HTTP client module {finding.extra.get('module', finding.symbol)} outside a transport adapter.", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = RawHttpClientOwnershipRule()
