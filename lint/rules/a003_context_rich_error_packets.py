"""FILE: lint/rules/a003_context_rich_error_packets.py

PURPOSE: Defines A003 as the SDK's stable boundary-error context policy.
ROLE IN CODEBASE: Keeps error kind, behavior, runtime details, and repair context discoverable.
ARCHITECTURE NOTE: Detection inspects literal error-class schemas without constructing exceptions.
FUNCTION INVENTORY: ErrorPacketAnalyzer and ContextRichErrorPacketsRule inspect/report.
COMMON MODIFICATION PATTERNS: Change canonical fields and diagnostics together; rerun A003.
WHAT NOT TO DO: Do not accept opaque details mappings, execute SDK constructors, or hide fields.
KNOWN EDGE CASES: The root VidbyteSdkError is the inherited contract and is exempt.
RELATED DOCS: docs/design/agent-native-lint-rules.md
TESTS: Exercised by python lint/run.py --rule A003.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

ERROR_PREFIX = "vidbyte/lib/errors/"
CANONICAL_DIAGNOSTIC_FIELDS = (
    "error_kind",
    "expected",
    "actual",
    "safe_runtime_details",
    "likely_causes",
    "repair_approaches",
    "related_docs",
    "relevant_tests",
)


class ErrorPacketAnalyzer:
    """Checks literal diagnostic field declarations on central SDK errors."""

    def analyze(self, source: SourceFile) -> list[tuple[int, str, tuple[str, ...]]]:
        # Finds error classes and resolves same-module schema inheritance deterministically.
        if source.tree is None:
            return []
        classes = {node.name: node for node in source.tree.body if isinstance(node, ast.ClassDef)}
        schemas = {name: self._schema(node) for name, node in classes.items()}
        findings: list[tuple[int, str, tuple[str, ...]]] = []
        for name, node in classes.items():
            if not name.endswith("Error") or name == "VidbyteSdkError":
                continue
            fields = self._resolved_fields(node, schemas, classes, set())
            missing = tuple(field for field in CANONICAL_DIAGNOSTIC_FIELDS if field not in fields)
            if missing:
                findings.append((node.lineno, name, missing))
        return findings

    def _schema(self, node: ast.ClassDef) -> frozenset[str]:
        # Extracts a class-local literal DIAGNOSTIC_FIELDS declaration.
        for item in node.body:
            targets = item.targets if isinstance(item, ast.Assign) else [item.target] if isinstance(item, ast.AnnAssign) else []
            if not any(isinstance(target, ast.Name) and target.id == "DIAGNOSTIC_FIELDS" for target in targets):
                continue
            value = item.value
            if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                return frozenset(element.value for element in value.elts if isinstance(element, ast.Constant) and isinstance(element.value, str))
        return frozenset()

    def _resolved_fields(self, node: ast.ClassDef, schemas: dict[str, frozenset[str]], classes: dict[str, ast.ClassDef], seen: set[str]) -> frozenset[str]:
        # Combines local fields with resolvable same-module base-class schemas.
        if node.name in seen:
            return frozenset()
        seen.add(node.name)
        fields = set(schemas[node.name])
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in classes:
                fields.update(self._resolved_fields(classes[base.id], schemas, classes, seen))
        return frozenset(fields)


class ContextRichErrorPacketsRule(Rule):
    """Requires central SDK boundary errors to declare a context-rich packet schema."""

    id = "A003"
    name = "context-rich-error-packets"
    severity = "blocking"
    summary = "Boundary errors expose stable diagnostic fields for callers and repair agents."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans only the central error hierarchy and preserves one finding per class.
        findings: list[Finding] = []
        analyzer = ErrorPacketAnalyzer()
        for source in catalog.python_files():
            if not source.rel.startswith(ERROR_PREFIX):
                continue
            for line, class_name, missing in analyzer.analyze(source):
                findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol=class_name, extra={"missing": ", ".join(missing)}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the exact schema fields required to make a boundary error repairable.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} error class {finding.symbol} lacks diagnostic field(s): {finding.extra.get('missing', 'context') }.", why_blocked="A boundary exception is often the only context that survives a failed provider, tool, permission, or persistence operation. If it exposes only a message or opaque dynamic details, a caller and a coding agent cannot distinguish expected behavior, observed behavior, safe runtime facts, likely causes, and the correct repair.", how_to_fix="Declare a literal `DIAGNOSTIC_FIELDS` tuple on the error class containing all canonical fields: error_kind, expected, actual, safe_runtime_details, likely_causes, repair_approaches, related_docs, and relevant_tests. Populate those fields or the safe `details` packet in the constructor without credentials, raw secrets, or unbounded provider text.", correct_examples=("vidbyte/lib/errors/base.py - central VidbyteSdkError hierarchy and bounded ProviderRequestError details.", "A new boundary error with a literal DIAGNOSTIC_FIELDS tuple and a typed constructor packet."), will_not_work=("Adding more prose to the exception message while leaving fields implicit.", "Putting arbitrary keys into a dynamic details mapping without declaring the stable schema."), verify=self.verify_command())


RULE = ContextRichErrorPacketsRule()
