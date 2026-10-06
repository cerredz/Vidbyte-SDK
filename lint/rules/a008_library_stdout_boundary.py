"""FILE: lint/rules/a008_library_stdout_boundary.py

PURPOSE: Defines A008 as the SDK's importable-library stdout boundary policy.
ROLE IN CODEBASE: Keeps human-facing console output at the designated CLI adapter.
ARCHITECTURE NOTE: Detection reports builtin print calls from the shared package ASTs.
FUNCTION INVENTORY: StdoutAnalyzer and LibraryStdoutBoundaryRule inspect/report.
COMMON MODIFICATION PATTERNS: Change console boundaries and diagnostics together; rerun A008.
WHAT NOT TO DO: Do not flag strings, logger calls, or CLI-owned output.
KNOWN EDGE CASES: A method named print is allowed until it invokes builtin print.
RELATED DOCS: docs/design/agent-native-lint-rules.md
TESTS: Exercised by python lint/run.py --rule A008.
"""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

ALLOWED_STDOUT_PREFIXES = ("vidbyte/cli/",)


class StdoutAnalyzer:
    """Finds actual builtin print calls in one non-CLI SDK module."""

    def analyze(self, source: SourceFile) -> list[int]:
        # Returns call locations while ignoring strings and designated CLI adapters.
        if source.tree is None or source.rel.startswith(ALLOWED_STDOUT_PREFIXES):
            return []
        return [node.lineno for node in ast.walk(source.tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"]


class LibraryStdoutBoundaryRule(Rule):
    """Rejects builtin stdout writes outside the SDK's CLI console boundary."""

    id = "A008"
    name = "library-stdout-boundary"
    severity = "blocking"
    summary = "Importable SDK modules return data or use structured logging instead of print()."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans tracked production modules and keeps CLI output explicitly allowed.
        findings: list[Finding] = []
        analyzer = StdoutAnalyzer()
        for source in catalog.python_files():
            for line in analyzer.analyze(source):
                findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol="print", extra={"boundary": "vidbyte/cli/"}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Connects accidental stdout to library composability and agent diagnostics.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} calls builtin print() outside the CLI boundary.", why_blocked="Importable library code can be embedded in servers, notebooks, tests, and agent runtimes where unsolicited stdout corrupts protocol output and bypasses structured observability. A caller should decide how a result or failure is presented.", how_to_fix="Return the value to the caller, raise a typed SDK error, or emit a structured logger/tracer event. If the behavior is genuinely human-facing CLI output, move the presentation into `vidbyte/cli/` and keep the SDK layer data-oriented.", correct_examples=("vidbyte/cli/__init__.py - owns human-facing command output.", "vidbyte/lib/runners/text.py - should return model data to its caller rather than write stdout."), will_not_work=("Wrapping print in another helper or using a suppression comment.", "Adding a file-local console exception instead of moving the boundary to the CLI adapter."), verify=self.verify_command())


RULE = LibraryStdoutBoundaryRule()
