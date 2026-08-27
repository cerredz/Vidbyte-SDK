"""FILE: lint/rules/a001_agent_readable_file_headers.py

PURPOSE: Defines A001 as the SDK's structured Python file-header policy.
ROLE IN CODEBASE: Keeps purpose, ownership, architecture, and repair context discoverable.
ARCHITECTURE NOTE: Detection reads module docstrings from the shared source catalogue.
FUNCTION INVENTORY: FileHeaderAnalyzer and AgentReadableFileHeadersRule inspect/report.
COMMON MODIFICATION PATTERNS: Change required fields and diagnostics together; rerun A001.
WHAT NOT TO DO: Do not accept arbitrary prose, import modules, or mutate source headers.
KNOWN EDGE CASES: Missing or empty canonical fields produce one finding per file.
RELATED DOCS: docs/design/agent-native-lint-rules.md
TESTS: Exercised by python lint/run.py --rule A001.
"""

from __future__ import annotations

import ast
import re

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

HEADER_SCAN_LINES = 80
REQUIRED_FIELDS = (
    "PURPOSE:",
    "ROLE IN CODEBASE:",
    "ARCHITECTURE NOTE:",
    "COMMON MODIFICATION PATTERNS:",
    "KNOWN EDGE CASES:",
    "RELATED DOCS:",
    "TESTS:",
)


class FileHeaderAnalyzer:
    """Checks the canonical context fields in one module's opening docstring."""

    def analyze(self, source: SourceFile) -> tuple[str, ...]:
        # Returns canonical fields that are absent or empty from the file header.
        header = self._header_text(source)
        return tuple(field for field in REQUIRED_FIELDS if not self._has_value(header, field))

    def _header_text(self, source: SourceFile) -> str:
        # Reads only the opening docstring or bounded source prefix, never later code.
        if source.tree is not None:
            module_docstring = ast.get_docstring(source.tree, clean=False)
            if module_docstring is not None:
                return module_docstring
        return "\n".join(source.text.splitlines()[:HEADER_SCAN_LINES])

    def _has_value(self, header: str, field: str) -> bool:
        # Requires a non-empty value after an exact canonical marker.
        pattern = rf"(?im)^\s*{re.escape(field)}\s*(\S.*)$"
        return re.search(pattern, header) is not None


class AgentReadableFileHeadersRule(Rule):
    """Requires tracked Python files to expose structured maintenance context."""

    id = "A001"
    name = "agent-readable-file-headers"
    severity = "blocking"
    summary = "SDK Python file headers explain purpose, ownership, architecture, and repair context."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans every tracked Python file and reports one complete header repair per file.
        findings: list[Finding] = []
        analyzer = FileHeaderAnalyzer()
        for source in catalog.all_python_files():
            missing = analyzer.analyze(source)
            if missing:
                findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=1, source_line=source.line_at(1), symbol=source.rel, extra={"missing": ", ".join(missing)}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Names every missing field so one header edit supplies the full context packet.
        missing = finding.extra.get("missing", "required header fields")
        return Diagnostic(what_happened=f"{finding.rel_path} is missing structured header field(s): {missing}.", why_blocked="Agents use the file header as the first compressed explanation of what a module owns and how it may be changed. Without ownership, edge-case, and verification context, an agent has to infer boundaries from imports and callers before making a safe edit.", how_to_fix="Add a module docstring header with non-empty PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES, RELATED DOCS, and TESTS fields. Keep the guidance specific to this module and update it when the module's contract changes.", correct_examples=("lint/core/registry.py - complete structured header with role, modification patterns, edge cases, docs, and tests.", "vidbyte/lib/errors/base.py - module-level architecture and relation context."), will_not_work=("Adding a one-line summary or moving the explanation into a distant README.", "Copying a generic header without documenting this module's ownership and failure modes."), verify=self.verify_command())


RULE = AgentReadableFileHeadersRule()
