"""FILE: lint/rules/s010_transport_parity.py

PURPOSE: Enforces async/sync parity between runner/tool methods and HTTP transports.
ROLE IN CODEBASE: Prevents coroutine objects from being consumed as responses and blocking I/O on loops.
ARCHITECTURE NOTE: The rule follows self transport defaults and their use/passthrough.
FUNCTION INVENTORY: TransportParityAnalyzer inspects each class in two passes.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md
TESTS: Exercised by python lint/run.py --rule S010.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

SCOPED_PREFIXES = ("vidbyte/lib/runners/", "vidbyte/providers/", "vidbyte/tools/builtins/")
ASYNC_TRANSPORT = "HttpTransport"
SYNC_TRANSPORT = "SyncHttpTransport"
TRANSPORT_METHODS = frozenset({"request", "request_bytes", "stream_request", "upload_multipart"})


class TransportParityAnalyzer:
    """Finds transport defaults used from methods with incompatible execution modes."""

    def analyze(self, source: SourceFile) -> list[tuple[int, str, str]]:
        # Analyzes each class after first resolving its self transport assignments.
        hits: list[tuple[int, str, str]] = []
        if source.tree is None:
            return hits
        for node in source.tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bindings = self._bindings(node)
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    hits.extend(self._method_hits(member, bindings))
        return hits

    def _bindings(self, node: ast.ClassDef) -> dict[str, str]:
        # Maps self attributes to the concrete default transport constructor in the class.
        bindings: dict[str, str] = {}
        for child in ast.walk(node):
            if not isinstance(child, (ast.Assign, ast.AnnAssign)):
                continue
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            constructor = self._constructor(child.value)
            for target in targets:
                if constructor and isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    bindings[target.attr] = constructor
        return bindings

    def _method_hits(self, node: ast.FunctionDef | ast.AsyncFunctionDef, bindings: dict[str, str]) -> list[tuple[int, str, str]]:
        # Flags direct transport calls and passthrough into provider methods with wrong mode.
        async_method = isinstance(node, ast.AsyncFunctionDef)
        hits: list[tuple[int, str, str]] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            used = self._bound_attrs(child, bindings)
            for attribute, kind in used:
                direct_method = child.func.attr if isinstance(child.func, ast.Attribute) and isinstance(child.func.value, ast.Attribute) and child.func.value.attr == attribute else ""
                if kind == ASYNC_TRANSPORT and not async_method and (direct_method in TRANSPORT_METHODS or self._passed_to_call(child, attribute)):
                    hits.append((child.lineno, attribute, "async transport used by synchronous method"))
                if kind == SYNC_TRANSPORT and async_method and (direct_method in TRANSPORT_METHODS or self._passed_to_call(child, attribute)):
                    hits.append((child.lineno, attribute, "blocking transport used by async method"))
                if kind == ASYNC_TRANSPORT and direct_method in TRANSPORT_METHODS - {"request"}:
                    hits.append((child.lineno, attribute, f"{kind} has no {direct_method} method"))
        return list(dict.fromkeys(hits))

    def _bound_attrs(self, node: ast.Call, bindings: dict[str, str]) -> list[tuple[str, str]]:
        # Returns every bound self transport attribute referenced by this call.
        referenced = {(child.attr, bindings[child.attr]) for child in ast.walk(node) if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id == "self" and child.attr in bindings}
        return sorted(referenced)

    def _passed_to_call(self, node: ast.Call, attribute: str) -> bool:
        # True when self.<attribute> is an argument rather than the call receiver.
        arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
        return any(isinstance(item, ast.Attribute) and isinstance(item.value, ast.Name) and item.value.id == "self" and item.attr == attribute for item in arguments)

    def _constructor(self, node: ast.expr | None) -> str:
        # Finds a known transport constructor through direct calls and `injected or Default()`.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {ASYNC_TRANSPORT, SYNC_TRANSPORT}:
            return node.func.id
        if isinstance(node, ast.BoolOp):
            for value in node.values:
                resolved = self._constructor(value)
                if resolved:
                    return resolved
        return ""


class TransportParityRule(Rule):
    """Requires each SDK HTTP transport to match its caller's execution model."""

    id = "S010"
    name = "transport-parity"
    severity = "blocking"
    summary = "Async callers use HttpTransport; synchronous callers use SyncHttpTransport."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans runner/provider/tool classes whose defaults own transport mode.
        findings: list[Finding] = []
        analyzer = TransportParityAnalyzer()
        for source in catalog.python_files():
            if not source.rel.startswith(SCOPED_PREFIXES):
                continue
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=attribute, extra={"reason": reason}) for line, attribute, reason in analyzer.analyze(source))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Provides the parity repair without encouraging thread shims around the wrong API.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} has {finding.extra.get('reason', 'transport mismatch')} for self.{finding.symbol}.", why_blocked="A synchronous method receives a coroutine instead of HttpResponse, or an async event loop performs blocking urllib I/O. Both failures violate provider contracts and can surface only for particular modalities.", how_to_fix="Use HttpTransport only through awaited async methods. Use SyncHttpTransport for synchronous provider/runner methods and its request_bytes/upload_multipart/stream_request APIs. Align the constructor annotation, default, provider protocol, and call together.", correct_examples=("vidbyte/lib/http/transport.py - separate transport classes and methods", "vidbyte/lib/runners/text.py - async text runner transport flow"), will_not_work=("Calling asyncio.run inside an SDK method or hiding blocking calls in an async function.", "Changing only the type annotation while retaining the wrong constructor."), verify=self.verify_command())


RULE = TransportParityRule()
