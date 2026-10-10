"""FILE: lint/rules/a009_readme_size_limit.py

PURPOSE: Defines A009, the ceiling on how long a folder README.md may grow, so an agent can still read it in full before it changes the folder.
ROLE IN CODEBASE: Bounds the `## Notes for agents` section that the notes stage of the @claude workflow, .github/workflows/claude.yml, appends to after every review, and forces Claude to compact the notes once a README reaches its ceiling.
ARCHITECTURE NOTE: Detection measures the characters of every tracked README from the shared source catalogue and never parses Markdown; the finding lands on the notes heading because that section is the part a repair compacts.
FUNCTION INVENTORY: ReadmeSizeAnalyzer.analyze() reports READMEs over their ceiling; ReadmeSizeLimitRule.check()/explain() report and diagnose them.
COMMON MODIFICATION PATTERNS: Lower a LEGACY_CEILINGS entry after its README shrinks, and delete the entry once the file fits under MAXIMUM_CHARACTERS; never raise one.
WHAT NOT TO DO: Do not add a README to LEGACY_CEILINGS to make a regression pass, do not exempt more files, and do not count Markdown structure instead of characters.
KNOWN EDGE CASES: The root README.md is the package's PyPI description and is never written by the notes workflow, so it is exempt; two folder READMEs predate the rule above 40,000 characters and keep a fixed ceiling of their own.
RELATED DOCS: docs/design/claude-review-agents.md
TESTS: Exercised by python lint/run.py --rule A009 and tests/test_readme_size_limit.py.
"""

from __future__ import annotations

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

MAXIMUM_CHARACTERS = 40_000
# Room a compaction leaves under a README's ceiling, so the next notes fit before it fails again.
COMPACTION_HEADROOM = 10_000
NOTES_HEADING = "## Notes for agents"
# The PyPI long description: the notes workflow never writes it, and its audience sets its length.
EXEMPT_READMES = frozenset({"README.md"})
# Folder READMEs that were already over MAXIMUM_CHARACTERS when this rule began (50,278 and
# 40,506 characters). Each ceiling is that size rounded up plus about 15,000 characters of
# notes, so these folders can still collect notes; lower an entry as the file shrinks.
LEGACY_CEILINGS = {
    "vidbyte/agents/codex/README.md": 65_000,
    "vidbyte/providers/README.md": 55_000,
}


class ReadmeSizeAnalyzer:
    """Reports each tracked README.md that is longer than its ceiling."""

    def analyze(self, catalog: SourceCatalog) -> list[Finding]:
        # Measures every non-exempt README against its own ceiling and anchors at the notes.
        findings: list[Finding] = []
        for source in catalog.readmes():
            if source.rel in EXEMPT_READMES:
                continue
            ceiling = LEGACY_CEILINGS.get(source.rel, MAXIMUM_CHARACTERS)
            if len(source.text) <= ceiling:
                continue
            line = self._notes_line(source)
            findings.append(Finding(rule_id=ReadmeSizeLimitRule.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol="README.md", extra={"characters": str(len(source.text)), "ceiling": str(ceiling), "target": str(ceiling - COMPACTION_HEADROOM)}))
        return findings

    def _notes_line(self, source: SourceFile) -> int:
        # Points at the notes heading when one exists, otherwise at the top of the file.
        for number, text in enumerate(source.text.splitlines(), 1):
            if text.strip() == NOTES_HEADING:
                return number
        return 1


class ReadmeSizeLimitRule(Rule):
    """Caps every folder README.md at a size an agent can read in full before editing."""

    id = "A009"
    name = "readme-size-limit"
    severity = "blocking"
    summary = "Every tracked folder README.md holds at most 40,000 characters, or its fixed legacy ceiling."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Delegates measurement to the analyzer so detection and diagnostics stay separate.
        return ReadmeSizeAnalyzer().analyze(catalog)

    def explain(self, finding: Finding) -> Diagnostic:
        # Names the file's own ceiling and the size a compaction must reach.
        count = int(finding.extra.get("characters", "0"))
        ceiling = int(finding.extra.get("ceiling", str(MAXIMUM_CHARACTERS)))
        target = int(finding.extra.get("target", str(ceiling - COMPACTION_HEADROOM)))
        return Diagnostic(
            what_happened=f"{finding.rel_path} is {count:,} characters long; its ceiling is {ceiling:,}. Compact it to at most {target:,} characters.",
            why_blocked="Agents read a folder's README.md in full before they change that folder, and the notes stage of the @claude workflow appends a note to it after every review comment in the folder. Without a ceiling those notes grow until the README costs more context than it saves. The ceiling and the compaction it forces come from docs/design/claude-review-agents.md.",
            how_to_fix=f"Compact the closing `{NOTES_HEADING}` section until the whole file is at most {target:,} characters, so the next notes have room before the ceiling. First drop notes whose lesson a check now enforces, then merge notes that teach the same lesson into one, then shorten the oldest notes. Leave the sections above the notes as their authors wrote them; if the file is too long even without notes, shorten the folder's documentation in a change of its own.",
            correct_examples=("vidbyte/lib/README.md - a folder README well under the ceiling.", "lint/README.md - a folder README whose sections stay short and factual."),
            will_not_work=("Raising the A009 allowance in lint/baseline.json or adding the README to LEGACY_CEILINGS; both hide growth the rule exists to stop.", "Moving the notes into a separate file the README links to; the notes exist so that an agent reads them together with the README it already reads.", "Deleting the notes section outright; it holds lessons the next change needs."),
            verify=self.verify_command(),
        )


RULE = ReadmeSizeLimitRule()
