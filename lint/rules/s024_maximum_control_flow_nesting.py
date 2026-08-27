"""FILE: lint/rules/s024_maximum_control_flow_nesting.py

PURPOSE: Defines S024 as the SDK's maximum control-flow nesting policy.
ROLE IN CODEBASE: Keeps branching depth within the context an agent can hold.
ARCHITECTURE NOTE: Detection is a side-effect-free AST walk over SourceCatalog.
FUNCTION INVENTORY: NestingAnalyzer and MaximumControlFlowNestingRule scan/report.
COMMON MODIFICATION PATTERNS: Change counted constructs and diagnostics together; rerun S024.
WHAT NOT TO DO: Do not import SDK modules, count unrelated expressions, or hide findings.
KNOWN EDGE CASES: Elif branches share if depth; else/finally/handlers add no level.
RELATED DOCS: docs/design/agent-native-lint-rules.md
TESTS: Exercised by python lint/run.py --rule S024.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

MAX_NESTING_DEPTH = 3
CONTROL_NODES = (ast.If, ast.For, ast.AsyncFor, ast.Try, ast.With, ast.AsyncWith, ast.Match)


class NestingAnalyzer:
    """Finds statement-level control-flow nodes beyond the allowed depth."""

    def analyze(self, source: SourceFile) -> list[tuple[int, str, int]]:
        # Walks module statements while resetting depth at function boundaries.
        if source.tree is None:
            return []
        self._source = source
        self._findings: list[tuple[int, str, int]] = []
        self._visit_block(source.tree.body, 0)
        return self._findings

    def _visit_block(self, nodes: list[ast.stmt], depth: int) -> None:
        # Visits a sequence of statements at one semantic nesting depth.
        for node in nodes:
            self._visit_node(node, depth)

    def _visit_node(self, node: ast.AST, depth: int) -> None:
        # Dispatches special control-flow branches without double-counting them.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._visit_block(node.body, 0)
            return
        if isinstance(node, ast.If):
            self._visit_if(node, depth)
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            next_depth = self._record(node, depth)
            self._visit_block(node.body, next_depth)
            self._visit_block(node.orelse, next_depth)
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            next_depth = self._record(node, depth)
            self._visit_block(node.body, next_depth)
            return
        if isinstance(node, ast.Try):
            next_depth = self._record(node, depth)
            self._visit_block(node.body, next_depth)
            for handler in node.handlers:
                self._visit_block(handler.body, next_depth)
            self._visit_block(node.orelse, next_depth)
            self._visit_block(node.finalbody, next_depth)
            return
        if isinstance(node, ast.Match):
            next_depth = self._record(node, depth)
            for case in node.cases:
                self._visit_block(case.body, next_depth)
            return
        for child in ast.iter_child_nodes(node):
            self._visit_node(child, depth)

    def _visit_if(self, node: ast.If, depth: int) -> None:
        # Treats elif as a sibling branch while retaining nested else semantics.
        next_depth = self._record(node, depth)
        self._visit_block(node.body, next_depth)
        if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
            self._visit_if(node.orelse[0], depth)
        else:
            self._visit_block(node.orelse, next_depth)

    def _record(self, node: ast.AST, depth: int) -> int:
        # Records a control node only when entering it exceeds the policy depth.
        next_depth = depth + 1
        if next_depth > MAX_NESTING_DEPTH:
            self._findings.append((node.lineno, type(node).__name__.lower(), next_depth))
        return next_depth


class MaximumControlFlowNestingRule(Rule):
    """Rejects control-flow nesting deeper than three semantic levels."""

    id = "S024"
    name = "maximum-control-flow-nesting"
    severity = "blocking"
    summary = "Control-flow nesting stays at or below three semantic levels."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans every parsed production module without executing package code.
        findings: list[Finding] = []
        analyzer = NestingAnalyzer()
        for source in catalog.python_files():
            for line, construct, depth in analyzer.analyze(source):
                findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=construct, extra={"construct": construct, "depth": str(depth), "limit": str(MAX_NESTING_DEPTH)}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Gives an agent the extraction repair and the exact violated threshold.
        depth = finding.extra.get("depth", "unknown")
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} enters {finding.extra.get('construct', 'control')} nesting at depth {depth}.", why_blocked="Deeply nested branches force an agent to retain too many simultaneous conditions, cleanup paths, and state assumptions. That increases repair errors at precisely the policy-heavy points this SDK must keep inspectable.", how_to_fix="Extract one coherent branch into a named private method, use an early return/guard clause, or move a state transition into a small class method. Keep the extracted method at three control-flow levels or fewer; do not flatten unrelated logic into a generic helper.", correct_examples=("vidbyte/tools/builtins/operations/clients/_base.py - small request/response boundary methods", "vidbyte/lib/dataclasses/config.py - validation leaves split by responsibility"), will_not_work=("Adding a suppression or raising the depth limit in the rule.", "Adding boolean flags that preserve the same nested decision tree."), verify=self.verify_command())


RULE = MaximumControlFlowNestingRule()
