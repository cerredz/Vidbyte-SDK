"""FILE: lint/rules/s062_no_implicit_string_concatenation.py

PURPOSE: Defines S062, which rejects string literals built from two or more adjacent literals, the "strings of strings" shape.
ROLE IN CODEBASE: Keeps every piece of text, above all model-facing prompt and Jev question text, written as one literal a reader can see whole.
ARCHITECTURE NOTE: Detection tokenizes each tracked Python file from SourceCatalog; the AST cannot see this shape because the parser merges adjacent literals into one constant.
FUNCTION INVENTORY: ImplicitConcatenationScanner finds each group of adjacent literals; NoImplicitStringConcatenationRule reports one finding per group.
COMMON MODIFICATION PATTERNS: Change the token model and the diagnostic together; rerun the focused rule.
WHAT NOT TO DO: Do not import runtime packages, mutate source, suppress findings, or count a group more than once.
KNOWN EDGE CASES: Comments and non-logical newlines between literals still join them, so they do not end a group; Python 3.12+ f-strings arrive as start/middle/end tokens and count as one literal.
RELATED DOCS: PR #456 review comment 4108971007 ("I don't want there to be strings of strings. I just want there to be one big string.").
TESTS: Exercised by python lint/run.py --rule S062.
"""

from __future__ import annotations

import io
import token
import tokenize

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

# Tokens that may sit between two adjacent literals without ending the concatenation.
JOINING_TOKENS = frozenset({token.NL, token.COMMENT})
# Python 3.12+ splits f-strings (and 3.14+ t-strings) into start/middle/end tokens.
LITERAL_START_TOKENS = frozenset(value for value in (getattr(token, "FSTRING_START", None), getattr(token, "TSTRING_START", None)) if value is not None)
LITERAL_END_TOKENS = frozenset(value for value in (getattr(token, "FSTRING_END", None), getattr(token, "TSTRING_END", None)) if value is not None)


class ImplicitConcatenationScanner:
    """Finds each run of two or more adjacent string literals in one source file."""

    def scan(self, source: SourceFile) -> list[tuple[int, int]]:
        # Returns (first line, literal count) for every group of adjacent literals.
        groups: list[tuple[int, int]] = []
        first_line = 0
        count = 0
        depth = 0
        for item in tokenize.generate_tokens(io.StringIO(source.text).readline):
            if depth:
                depth += (item.type in LITERAL_START_TOKENS) - (item.type in LITERAL_END_TOKENS)
                continue
            if item.type == token.STRING or item.type in LITERAL_START_TOKENS:
                depth = int(item.type in LITERAL_START_TOKENS)
                first_line = first_line if count else item.start[0]
                count += 1
                continue
            if item.type in JOINING_TOKENS:
                continue
            if count > 1:
                groups.append((first_line, count))
            count = 0
        return groups


class NoImplicitStringConcatenationRule(Rule):
    """Rejects a string literal that is written as several adjacent literals."""

    id = "S062"
    name = "no-implicit-string-concatenation"
    severity = "blocking"
    summary = "Each string is one literal, never several adjacent literals that Python silently joins."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Scans every tracked Python file, because the review asked for this rule in all files and folders.
        findings: list[Finding] = []
        scanner = ImplicitConcatenationScanner()
        for source in catalog.all_python_files():
            if source.tree is None:
                continue
            for line, count in scanner.scan(source):
                findings.append(Finding(rule_id=self.id, rel_path=source.rel, line=line, source_line=source.line_at(line), symbol="implicit-concatenation", extra={"literals": str(count)}))
        return findings

    def explain(self, finding: Finding) -> Diagnostic:
        # Tells an agent how to merge the group into one literal and where the rule came from.
        return Diagnostic(
            what_happened=f"{finding.rel_path}:{finding.line} writes one string as {finding.extra.get('literals', 'several')} adjacent literals that Python joins implicitly.",
            why_blocked="Adjacent literals hide where one sentence ends and the next begins, drop or double spaces at every seam, and turn a missing comma in a list into a silently merged item. The owner asked for this in review of PR #456 (comment 4108971007): model-facing text such as Jev questions must be one big string, not strings of strings.",
            how_to_fix="Merge the pieces into a single string literal on one line, and keep one space between sentences. For a long f-string, write one f-string; for text a model reads, consider a prompt asset under vidbyte/prompts/prompts/ instead of an inline literal.",
            correct_examples=("vidbyte/lib/jev/preflight/clarity.py - every question brief and criterion is one literal",),
            will_not_work=("Joining the pieces with + or ''.join(), which keeps the strings-of-strings shape.", "Adding a suppression or raising the S062 baseline."),
            verify=self.verify_command(),
        )


RULE = NoImplicitStringConcatenationRule()
