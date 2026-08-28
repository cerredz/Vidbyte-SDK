"""FILE: lint/rules/s056_retryable_idempotent_methods.py

PURPOSE: Requires the HTTP transports' retry loops to guard non-idempotent methods with a key.
ROLE IN CODEBASE: Keeps vidbyte/lib/http/transport.py from silently losing its idempotency guard.
ARCHITECTURE NOTE: A fixed-surface structural check (2 known classes), not a repo-wide call-site
    scan, per the custom-rule quality bar in docs/design/lint-rule-catalog-expansion.md section 13.
FUNCTION INVENTORY: RetryableIdempotentMethodsRule confirms both transport classes accept and use idempotency_key.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/lint-rule-catalog-expansion.md
TESTS: Exercised by python lint/run.py --rule S056.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

TRANSPORT_PATH = "vidbyte/lib/http/transport.py"
GUARDED_CLASSES = ("HttpTransport", "SyncHttpTransport")


def _request_method(class_node: ast.ClassDef) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    # Returns the class's request() method definition, sync or async.
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "request":
            return node
    return None


def _param_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    # Returns every declared parameter name including keyword-only ones.
    return {arg.arg for arg in (*func.args.posonlyargs, *func.args.args, *func.args.kwonlyargs)}


class RetryableIdempotentMethodsRule(Rule):
    """Requires HttpTransport/SyncHttpTransport.request() to accept an idempotency_key parameter."""

    id = "S056"
    name = "retryable-idempotent-methods"
    severity = "blocking"
    summary = "Retrying HTTP transports declare an idempotency_key parameter guarding non-idempotent methods."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Confirms both known transport classes still declare the guard parameter.
        findings: list[Finding] = []
        target = next((source for source in catalog.python_files() if source.rel == TRANSPORT_PATH), None)
        if target is None or target.tree is None:
            return findings
        classes = {node.name: node for node in target.tree.body if isinstance(node, ast.ClassDef)}
        for class_name in GUARDED_CLASSES:
            class_node = classes.get(class_name)
            if class_node is None:
                continue
            method = _request_method(class_node)
            if method is None:
                findings.append(Finding(rule_id=self.id, rel_path=target.rel, line=class_node.lineno, source_line=target.line_at(class_node.lineno), symbol=class_name, extra={"reason": "missing request() method"}))
                continue
            if "idempotency_key" not in _param_names(method):
                findings.append(Finding(rule_id=self.id, rel_path=target.rel, line=method.lineno, source_line=target.line_at(method.lineno), symbol=f"{class_name}.request", extra={"reason": "missing idempotency_key parameter"}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Points at the required parameter and the non-idempotent-method guard it backs.
        return Diagnostic(
            what_happened=f"{finding.rel_path}:{finding.line} - {finding.symbol} no longer declares the idempotency_key parameter its retry loop depends on.",
            why_blocked="A retry loop that repeats a POST/PATCH/PROTOCOL-mutating request after a network ambiguity (timeout, dropped response) can duplicate the underlying side effect even though the original request may have already succeeded; the idempotency_key parameter and the _IDEMPOTENT_METHODS check are what force a caller to make that duplication risk explicit before retry_count > 0 is honored for a non-idempotent method.",
            how_to_fix="Restore an idempotency_key: str | None = None parameter on request(), and keep the check that raises when retry_count > 0, method is not in _IDEMPOTENT_METHODS, and idempotency_key is None.",
            correct_examples=("vidbyte/lib/http/transport.py - HttpTransport.request()/SyncHttpTransport.request() both declare idempotency_key and validate it against _IDEMPOTENT_METHODS before honoring retry_count for a mutating method.",),
            will_not_work=("Removing the parameter and relying on callers to self-police retries.", "Renaming the parameter without updating this check's expectation."),
            verify=self.verify_command(),
        )


RULE = RetryableIdempotentMethodsRule()
