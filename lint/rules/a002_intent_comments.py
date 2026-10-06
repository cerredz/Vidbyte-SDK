"""FILE: lint/rules/a002_intent_comments.py

PURPOSE: Defines A002 as the SDK's load-bearing intent-comment policy.
ROLE IN CODEBASE: Makes retry, policy, persistence, state, and boundary intent visible to agents.
ARCHITECTURE NOTE: Detection uses function ASTs and a bounded nearby comment window.
FUNCTION INVENTORY: IntentAnalyzer and IntentCommentsRule identify/report missing intent markers.
COMMON MODIFICATION PATTERNS: Change policy vocabulary and diagnostics together; rerun A002.
WHAT NOT TO DO: Do not require comments on every function or accept empty intent markers.
KNOWN EDGE CASES: Generic helpers are ignored; markers must be near the function's leading logic.
RELATED DOCS: docs/design/agent-native-lint-rules.md
TESTS: Exercised by python lint/run.py --rule A002.
"""

from __future__ import annotations

import ast
import re

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

INTENT_MARKER = re.compile(r"#\s*@intent\s+\S+")
INTENT_WINDOW_LINES = 20
POLICY_TOKENS = {
    "retry": "retries",
    "backoff": "retries",
    "attempt": "retries",
    "permission": "permissions",
    "authorize": "permissions",
    "pricing": "pricing",
    "price": "pricing",
    "billing": "pricing",
    "redact": "redaction",
    "secret": "redaction",
    "persist": "persistence",
    "persistence": "persistence",
    "checkpoint": "persistence",
    "fallback": "fallback",
    "transition": "state transitions",
    "transport": "external boundaries",
    "request": "external boundaries",
    "fetch": "external boundaries",
    "send": "external boundaries",
    "urlopen": "external boundaries",
    "provider": "external boundaries",
    "subprocess": "external boundaries",
    "mcp": "external boundaries",
}


class IntentAnalyzer:
    """Finds policy-bearing functions without requiring universal comments."""

    def analyze(self, source: SourceFile) -> list[tuple[int, str, tuple[str, ...]]]:
        # Matches policy vocabulary and checks the bounded source window for intent.
        if source.tree is None:
            return []
        lines = source.text.splitlines()
        findings: list[tuple[int, str, tuple[str, ...]]] = []
        for node in ast.walk(source.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            categories = self._categories(node)
            if categories and not self._has_intent(node, lines):
                findings.append((node.lineno, node.name, categories))
        return findings

    def _categories(self, node: ast.AST) -> tuple[str, ...]:
        # Returns distinct policy categories represented by executable identifiers.
        identifiers = [getattr(node, "name", "")]
        identifiers.extend(child.id for child in ast.walk(node) if isinstance(child, ast.Name))
        identifiers.extend(child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute))
        text = " ".join(part for name in identifiers if name for part in re.split(r"[_\.]+", name.lower()))
        return tuple(sorted({category for token, category in POLICY_TOKENS.items() if re.search(rf"\b{re.escape(token)}\b", text)}))

    def _has_intent(self, node: ast.AST, lines: list[str]) -> bool:
        # Accepts a non-empty @intent marker immediately around leading function logic.
        start = max(0, node.lineno - 4)
        end = min(len(lines), node.lineno + INTENT_WINDOW_LINES)
        return any(INTENT_MARKER.search(line) for line in lines[start:end])


class IntentCommentsRule(Rule):
    """Requires nearby intent comments on policy-bearing functions."""

    id = "A002"
    name = "intent-comments"
    severity = "blocking"
    summary = "Load-bearing policy logic carries a nearby non-empty @intent marker."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans tracked production functions and reports each missing intent block once.
        findings: list[Finding] = []
        analyzer = IntentAnalyzer()
        for source in catalog.python_files():
            for line, function, categories in analyzer.analyze(source):
                findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=function, extra={"categories": ", ".join(categories)}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Identifies the policy categories that need a compact intent explanation.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} function {finding.symbol} handles {finding.extra.get('categories', 'load-bearing policy')} but has no nearby non-empty @intent marker.", why_blocked="A future agent can see what a branch does but not why the boundary, fallback, persistence, or state transition must remain that way. That missing invariant encourages superficially plausible edits that break the policy under failure.", how_to_fix="Add a nearby comment block beginning with `# @intent <short-name>`, followed by the invariant, the reason it exists, and the failure mode a repair must preserve. Keep the comment next to the leading policy logic and update it when the contract changes.", correct_examples=("vidbyte/config/loader.py - @intent comments explain containment, translation, and early validation boundaries.", "vidbyte/tools/builtins/operations/clients/_base.py - @intent explains the shared publication-date normalization contract."), will_not_work=("Adding an empty `# @intent` marker or a generic TODO.", "Moving the explanation to a distant README or documenting each branch without the governing invariant."), verify=self.verify_command())


RULE = IntentCommentsRule()
