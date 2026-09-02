"""FILE: lint/rules/s019_cancellation_propagation.py

PURPOSE: Preserves asyncio cancellation through SDK async boundaries.
ROLE IN CODEBASE: Lets callers stop agent/provider/tool work and release resources promptly.
ARCHITECTURE NOTE: except Exception is safe because CancelledError inherits BaseException.
FUNCTION INVENTORY: CancellationVisitor inspects handlers inside async functions.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md
TESTS: Exercised by python lint/run.py --rule S019.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule


class CancellationVisitor(ast.NodeVisitor):
    """Collects swallowed CancelledError and unsafe bare/BaseException handlers."""

    def __init__(self) -> None:
        # Starts outside async scope with an empty handler fact list.
        self.async_depth = 0
        self.hits: list[tuple[int, str]] = []

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # Tracks only handlers that can intercept task cancellation.
        self.async_depth += 1
        self.generic_visit(node)
        self.async_depth -= 1

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # Requires re-raise for explicit cancellation and broad BaseException catches.
        if self.async_depth:
            kind = self._kind(node.type)
            if kind and not any(isinstance(child, ast.Raise) for child in ast.walk(ast.Module(body=node.body, type_ignores=[]))):
                self.hits.append((node.lineno, kind))
        self.generic_visit(node)

    @staticmethod
    def _kind(node: ast.expr | None) -> str:
        # Classifies only handlers capable of catching cancellation.
        if node is None:
            return "bare except"
        if isinstance(node, ast.Tuple):
            names = [CancellationVisitor._kind(item) for item in node.elts]
            return next((name for name in names if name), "")
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
        return name if name in {"BaseException", "CancelledError"} else ""


class CancellationPropagationRule(Rule):
    """Requires async cancellation to propagate through SDK boundaries."""

    id = "S019"
    name = "cancellation-propagation"
    severity = "blocking"
    summary = "This rule preserves task cancellation as a control signal through asynchronous SDK boundaries. It inspects handlers that can catch CancelledError or broad BaseException paths inside provider, tool, runner, and transport work. A finding identifies a handler that consumes cancellation without re-raising it after any required cleanup. The contract ensures a caller can stop an abandoned run without leaving hidden work behind. Cancellation remains distinct from ordinary failure and must not be converted into a successful fallback merely because cleanup is inconvenient."
    impact = "Swallowed cancellation allows provider requests, streams, sockets, tasks, and usage accounting to continue after the caller has abandoned the run. Those operations can consume capacity, emit late side effects, or hold resources until an unrelated timeout eventually fires. The resulting behavior makes shutdown nondeterministic and can make a user believe work stopped when it did not. Because cancellation is represented by control flow rather than a normal result, converting it into fallback success is especially dangerous. A caller that cannot cancel one operation safely also cannot reliably enforce a run deadline or release resources under pressure."
    repair = "Identify whether the handler is responsible for cleanup or is only providing ordinary exception fallback. Add an explicit CancelledError path that performs required cleanup and re-raises, or re-raise immediately when no cleanup is owned there. Keep BaseException handling narrow and do not convert cancellation into a success, retry, or ordinary provider error result. Run the focused rule and the owning task, stream, timeout, and shutdown checks with cancellation injected during active work. Verify that cleanup completes without replacing the cancellation signal and that parent task groups still observe the cancellation."
    examples = (
        "An async context manager or task group that cleans up and then re-raises CancelledError",
        "A normal except Exception fallback that does not intercept modern asyncio cancellation",
    )
    will_not_work = (
        "Converting cancellation into a success or fallback result so the caller sees no exception.",
        "Catching BaseException only to make cleanup convenient and never restoring the cancellation signal.",
    )

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans every async production function for cancellation-capable handlers.
        findings: list[Finding] = []
        for source in catalog.python_files():
            if source.tree is None:
                continue
            visitor = CancellationVisitor()
            visitor.visit(source.tree)
            findings.extend(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=kind, extra={"kind": kind}) for line, kind in visitor.hits)
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Restores cancellation while leaving ordinary exception fallback policy separate.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} handles {finding.symbol} in async code without re-raising.", why_blocked=self.impact, how_to_fix=self.repair, correct_examples=self.examples, will_not_work=self.will_not_work, verify=self.verify_command())


RULE = CancellationPropagationRule()
