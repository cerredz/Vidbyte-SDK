"""FILE: lint/rules/s018_priced_operation_attempts.py

PURPOSE: Requires priced operation results to preserve actual HTTP attempt counts.
ROLE IN CODEBASE: Keeps retry-aware usage and billing metadata truthful.
ARCHITECTURE NOTE: Validation failures before I/O explicitly use attempts=0.
FUNCTION INVENTORY: OperationAttemptsVisitor inspects canonical result helper calls.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: docs/design/sdk-agent-facing-lint-suite.md
TESTS: Exercised by python lint/run.py --rule S018.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule

OPERATIONS_PREFIX = "vidbyte/tools/builtins/operations/"
RESULT_HELPERS = frozenset({"_executed_result", "_failed_result"})


class OperationAttemptsVisitor(ast.NodeVisitor):
    """Collects priced result helper calls missing an attempts keyword."""

    def __init__(self) -> None:
        # Starts an empty helper/location fact list.
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Requires attempt propagation on every canonical priced result helper.
        helper = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if helper in RESULT_HELPERS and not any(keyword.arg == "attempts" for keyword in node.keywords):
            self.hits.append((node.lineno, helper))
        self.generic_visit(node)


class PricedOperationAttemptsRule(Rule):
    """Requires priced operation success/failure metadata to carry attempt counts."""

    id = "S018"
    name = "priced-operation-attempts"
    severity = "blocking"
    summary = (
        "This rule keeps retry work visible in every priced operation result. "
        "It requires successful and failed results to carry the actual request attempts, while validation failures explicitly carry zero because no request occurred. "
        "A finding marks a canonical result helper call that can erase whether a provider succeeded immediately, retried, or exhausted its policy. "
        "The contract makes usage, pricing, and diagnostic records agree about the work the operation performed."
    )
    impact = (
        "Dropping the attempt count underreports provider work and can produce incorrect operation pricing or usage analytics. "
        "It also hides retry behavior from callers that need to distinguish a first-attempt result from a degraded or exhausted request. "
        "A hard-coded count can look correct in a happy path while becoming false as soon as transport policy changes. "
        "The missing metadata therefore weakens both financial correctness and the evidence needed to debug provider reliability."
    )
    repair = (
        "Trace each result path back to the request or validation boundary that produced it. "
        "Pass response.attempts or payload.attempts for executed requests, client.max_attempts when a retryable request exhausts its policy, and zero for validation failures before I/O. "
        "Keep all success and failure construction on the canonical priced helpers so result metadata cannot bypass the accounting contract. "
        "Run the focused rule and retry, pricing, and failure-path checks with first-attempt, retried, exhausted, and validation scenarios."
    )
    examples = (
        "vidbyte/tools/builtins/operations/search.py - success and failure attempt propagation",
        "vidbyte/tools/builtins/operations/base.py - canonical priced result helper contract",
    )
    will_not_work = (
        "Hard-coding attempts=1 after a retry-capable client call.",
        "Calling ToolResult directly or dropping into a parallel result builder to bypass the priced helper.",
    )

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans only operation implementations; the base helper defines the contract.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None or not source.rel.startswith(OPERATIONS_PREFIX) or source.rel.endswith("/base.py"):
                continue
            visitor = OperationAttemptsVisitor()
            visitor.visit(source.tree)
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=helper, extra={"helper": helper}) for line, helper in visitor.hits)
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Requires real response/client retry state rather than a guessed constant.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} calls {finding.symbol} without attempts=.", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = PricedOperationAttemptsRule()
