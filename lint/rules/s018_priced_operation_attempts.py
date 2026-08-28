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
    summary = "Every priced operation result passes actual or explicit zero attempts."

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
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} calls {finding.symbol} without attempts=.", why_blocked="Operation pricing and diagnostics distinguish validation failure, first-attempt success, and retry success/failure. Dropping attempts undercounts provider work and hides retry behavior.", how_to_fix="Pass attempts=payload.attempts/response.attempts for executed requests, client.max_attempts for exhausted request failures, and attempts=0 for validation failures before I/O.", correct_examples=("vidbyte/tools/builtins/operations/search.py - success/failure attempt propagation", "vidbyte/tools/builtins/operations/base.py - required helper contract"), will_not_work=("Hard-coding attempts=1 after a retry-capable client call.", "Calling ToolResult directly to bypass the priced helper."), verify=self.verify_command())


RULE = PricedOperationAttemptsRule()
