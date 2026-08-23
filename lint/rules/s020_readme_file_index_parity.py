"""FILE: lint/rules/s020_readme_file_index_parity.py

PURPOSE: Keeps opt-in README File Index sections synchronized with tracked files.
ROLE IN CODEBASE: Preserves folder discoverability for humans and coding agents.
ARCHITECTURE NOTE: Folders without a File Index heading are deliberately out of scope.
FUNCTION INVENTORY: ReadmeIndexAnalyzer extracts section entries and direct children.
COMMON MODIFICATION PATTERNS: Change scope, detection, and diagnostics together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or hide analyzer failures.
KNOWN EDGE CASES: Existing debt is count-ratcheted; analyzer and parse failures fail closed.
RELATED DOCS: agentic-engineering folder-readme principle
TESTS: Exercised by python lint/run.py --rule S020.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

INDEX_HEADING = "## File Index"
BACKTICK_FILE = re.compile(r"`([^`]+\.[A-Za-z0-9]+)`")
INDEXED_SUFFIXES = frozenset({".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"})
DOCUMENTATION_REFERENCES = frozenset({"README.md", "llms.txt"})


class ReadmeIndexAnalyzer:
    """Compares one declared README file index with tracked direct children."""

    def analyze(self, readme: SourceFile, tracked: tuple[str, ...]) -> list[tuple[str, str]]:
        # Reports missing tracked children and stale indexed entries using indexed suffixes.
        section = self._section(readme.text)
        if section is None:
            return []
        listed = {PurePosixPath(match).name for match in BACKTICK_FILE.findall(section) if PurePosixPath(match).suffix in INDEXED_SUFFIXES}
        listed -= DOCUMENTATION_REFERENCES
        if not listed:
            return []
        folder = PurePosixPath(readme.rel).parent
        suffixes = {PurePosixPath(name).suffix for name in listed}
        actual = {PurePosixPath(path).name for path in tracked if PurePosixPath(path).parent == folder and PurePosixPath(path).name != "README.md" and PurePosixPath(path).suffix in suffixes}
        return [(name, "tracked direct child missing from File Index") for name in sorted(actual - listed)] + [(name, "File Index entry is stale or not a direct tracked child") for name in sorted(listed - actual)]

    def _section(self, text: str) -> str | None:
        # Returns the File Index body through the next level-two heading.
        start = text.find(INDEX_HEADING)
        if start < 0:
            return None
        body_start = start + len(INDEX_HEADING)
        end = text.find("\n## ", body_start)
        return text[body_start:] if end < 0 else text[body_start:end]


class ReadmeFileIndexParityRule(Rule):
    """Requires declared README file indexes to remain complete and current."""

    id = "S020"
    name = "readme-file-index-parity"
    severity = "blocking"
    summary = "Existing README File Index sections match tracked direct children."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Applies opt-in parity to every tracked README declaring the heading.
        tracked = catalog.tracked_paths()
        findings: list[Finding] = []
        analyzer = ReadmeIndexAnalyzer()
        for readme in catalog.readmes():
            line = readme.text[: readme.text.find(INDEX_HEADING)].count("\n") + 1
            findings.extend(Finding(rule_id=self.id, rel_path=readme.rel, line=line, source_line=readme.line_at(line), symbol=name, extra={"reason": reason}) for name, reason in analyzer.analyze(readme, tracked))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Keeps declared folder navigation truthful without imposing new READMEs.
        return Diagnostic(what_happened=f"{finding.rel_path}:{finding.line} File Index entry {finding.symbol} is out of parity: {finding.extra.get('reason', 'index drift')}.", why_blocked="A File Index claims to be the local map for future agents. Missing or stale entries make architecture discovery probabilistic and encourage duplicate helpers/files.", how_to_fix="Add the tracked direct child to the existing File Index with its responsibility, or remove/rename the stale entry to match the file. Do not add a new File Index to unrelated folders for this rule.", correct_examples=("vidbyte/config/README.md - indexed folder documentation", "vidbyte/agents/multi/README.md - indexed multi-agent files"), will_not_work=("Listing nested descendants as direct children.", "Renaming a file without updating its existing index entry."), verify=self.verify_command())


RULE = ReadmeFileIndexParityRule()
