"""FILE: tests/test_grep_smart_case.py

PURPOSE: Proves item 3 of spec infinite-memory-context-economy on the shared GrepTool: the smart_case and context_lines constructor options, the call argument that still wins, the spec sentences each non-default option adds, the refusals of bad options, and that a GrepTool built without them is exactly main's.
ROLE IN CODEBASE: Root-level test of vidbyte/tools/builtins/code_search/grep.py and base.py (spec section 13: item 3 prior art is tests/test_code_search_tools.py).
ARCHITECTURE NOTE: A real tmp folder with one notes file; nothing is mocked. The main-behavior expectations are literal strings captured from main at base 0f2aeb48 (the default two context lines and the one-sentence description), so INV-3.1 cannot pass by changing the expectation.
FUNCTION INVENTORY: GrepDefaultsTests (AC-3.4, INV-3.1, row 9 constants); GrepSmartCaseTests (INV-3.2, AC-3.2, AC-3.3, EC-3.2); GrepContextLinesTests (INV-3.3, NFR-3.1); GrepOptionValidationTests (section 8.5 refusals, FR-3.1 spec sentences). _grep runs one call.
COMMON MODIFICATION PATTERNS: Add a pattern case as one _grep call against NOTES and compare the full output string.
WHAT NOT TO DO IN THIS FILE: 1. Do not compare with a second GrepTool's output as the only oracle for main behavior; the literal main strings are the oracle. 2. Do not add non-ASCII text to a literal expectation; the console may not round-trip it.
KNOWN EDGE CASES: The smart-case sentence's wording is not fixed by the spec, so only its presence and its subject are checked; the context sentence is fixed and checked verbatim.
RELATED DOCS: docs/spec/infinite-memory-context-economy/spec.md sections 6.1 (INV-3.x), 6.2 (AC-3.x), 8.5, 12.3 rows 9-10.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_grep_smart_case.py -q
"""

from __future__ import annotations

import asyncio
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.builtins.code_search import GrepTool
from vidbyte.tools.types import ToolCall, ToolStatus

NOTES = "Plans overview\nBasic plan 49 USD\nEnterprise plan 999 USD\nThe ProEnterprise tier is separate\nélan premium tier\nContact sales for volume\n"
MAIN_DESCRIPTION = "Search files for a literal string or regular expression."
# main's default output for the pattern "Enterprise" over NOTES: case-sensitive, two lines around each match.
MAIN_ENTERPRISE_OUTPUT = 'notes/plans.md:3\n1: Plans overview\n2: Basic plan 49 USD\n3: Enterprise plan 999 USD\n4: The ProEnterprise tier is separate\n5: élan premium tier\n\nnotes/plans.md:4\n2: Basic plan 49 USD\n3: Enterprise plan 999 USD\n4: The ProEnterprise tier is separate\n5: élan premium tier\n6: Contact sales for volume'
CONTEXT_SENTENCE = "When a call leaves context_lines out, it shows {n} lines around each match."


def _grep(tool: GrepTool, **arguments: Any) -> Any:
    return asyncio.run(tool.execute(ToolCall("grep", arguments)))


class _NotesFolder(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "notes").mkdir()
        (self.root / "notes" / "plans.md").write_text(NOTES, encoding="utf-8", newline="\n")

    def tearDown(self) -> None:
        self._tmp.cleanup()


class GrepDefaultsTests(_NotesFolder):
    def test_grep_built_without_the_new_options_equals_main(self) -> None:
        # AC-3.4, INV-3.1, INV-R.1: case-sensitive, two context lines, main's one-sentence spec; passing the defaults explicitly is the same tool.
        from vidbyte.tools.builtins.code_search.grep import GREP_DEFAULT_CONTEXT_LINES

        for tool in (GrepTool(self.root), GrepTool(self.root, smart_case=False, context_lines=GREP_DEFAULT_CONTEXT_LINES)):
            with self.subTest(tool=tool):
                self.assertEqual(_grep(tool, pattern="Enterprise").output, MAIN_ENTERPRISE_OUTPUT)
                self.assertEqual(_grep(tool, pattern="enterprise").output, "No matches found.")
                self.assertEqual(tool.spec().description, MAIN_DESCRIPTION)
                self.assertEqual(tool.spec(), GrepTool(self.root).spec())

    def test_the_shared_byte_cap_and_context_defaults_are_named_constants(self) -> None:
        # Rows 9-10: the literal defaults became constants with main's values, and the base default uses the byte constant.
        from vidbyte.tools.builtins.code_search.base import CODE_SEARCH_MAX_FILE_BYTES
        from vidbyte.tools.builtins.code_search.grep import GREP_DEFAULT_CONTEXT_LINES, GREP_MAX_CONTEXT_LINES

        self.assertEqual((CODE_SEARCH_MAX_FILE_BYTES, GREP_DEFAULT_CONTEXT_LINES, GREP_MAX_CONTEXT_LINES), (1_000_000, 2, 5))
        big = self.root / "notes" / "big.md"
        big.write_text("Enterprise\n" + "x" * CODE_SEARCH_MAX_FILE_BYTES, encoding="utf-8")
        self.assertNotIn("big.md", _grep(GrepTool(self.root), pattern="Enterprise").output, "the default byte cap no longer skips a file over CODE_SEARCH_MAX_FILE_BYTES")


class GrepSmartCaseTests(_NotesFolder):
    def test_a_lowercase_pattern_ignores_case_and_an_uppercase_one_matches_exactly(self) -> None:
        # INV-3.2, AC-3.1 and AC-3.2 at tool level: "enterprise plan" finds "Enterprise plan"; "ENTERPRISE" finds nothing.
        tool = GrepTool(self.root, smart_case=True, context_lines=0)
        self.assertEqual(_grep(tool, pattern="enterprise plan").output, "notes/plans.md:3\n3: Enterprise plan 999 USD")
        self.assertEqual(_grep(tool, pattern="Enterprise").output, "notes/plans.md:3\n3: Enterprise plan 999 USD\n\nnotes/plans.md:4\n4: The ProEnterprise tier is separate")
        self.assertEqual(_grep(tool, pattern="ENTERPRISE").output, "No matches found.")

    def test_a_letter_after_a_regex_backslash_does_not_count_as_uppercase(self) -> None:
        # AC-3.3, INV-3.2: \S, \A, \W and \D are escapes, not capitals, so these regexes still ignore case.
        tool = GrepTool(self.root, smart_case=True, context_lines=0)
        self.assertEqual(_grep(tool, pattern=r"\Senterprise", regex=True).output, "notes/plans.md:4\n4: The ProEnterprise tier is separate")
        self.assertEqual(_grep(tool, pattern=r"\Aenterprise plan", regex=True).output, "notes/plans.md:3\n3: Enterprise plan 999 USD")
        self.assertEqual(_grep(tool, pattern=r"enterprise\Wplan\W\d", regex=True).output, "notes/plans.md:3\n3: Enterprise plan 999 USD")
        self.assertEqual(_grep(tool, pattern=r"\Senterprise\D", regex=True).output, "notes/plans.md:4\n4: The ProEnterprise tier is separate")
        self.assertEqual(_grep(GrepTool(self.root, context_lines=0), pattern=r"\Senterprise", regex=True).output, "No matches found.", "precondition: without smart case the pattern is case-sensitive")

    def test_a_non_ascii_capital_makes_the_search_case_sensitive(self) -> None:
        # EC-3.2: str.isupper() counts the capital E-acute, so the lowercase line does not match.
        tool = GrepTool(self.root, smart_case=True, context_lines=0)
        self.assertEqual(_grep(tool, pattern="Élan").output, "No matches found.")
        self.assertEqual(_grep(tool, pattern="élan").metadata["count"], 1)


class GrepContextLinesTests(_NotesFolder):
    def test_zero_context_lines_gives_the_location_line_and_the_match_only(self) -> None:
        # INV-3.3, NFR-3.1: a call that omits context_lines uses the constructor's value; two lines per hit at 0.
        result = _grep(GrepTool(self.root, context_lines=0), pattern="Basic")
        self.assertEqual(result.output, "notes/plans.md:2\n2: Basic plan 49 USD")

    def test_a_call_argument_still_wins_and_is_clamped_as_on_main(self) -> None:
        # INV-3.3: the call's own context_lines beats the constructor's, clamped to 0..GREP_MAX_CONTEXT_LINES.
        tool = GrepTool(self.root, context_lines=0)
        self.assertEqual(_grep(tool, pattern="Basic", context_lines=1).output, "notes/plans.md:2\n1: Plans overview\n2: Basic plan 49 USD\n3: Enterprise plan 999 USD")
        clamped = _grep(tool, pattern="Plans", context_lines=99).output
        self.assertEqual(clamped, "notes/plans.md:1\n" + "\n".join(f"{n}: {line}" for n, line in enumerate(NOTES.splitlines()[:6], start=1)))
        self.assertEqual(_grep(tool, pattern="Plans", context_lines=-3).output, "notes/plans.md:1\n1: Plans overview")
        three = _grep(GrepTool(self.root, context_lines=3), pattern="volume").output
        self.assertEqual(three, "notes/plans.md:6\n" + "\n".join(f"{n}: {line}" for n, line in enumerate(NOTES.splitlines(), start=1) if n >= 3))


class GrepOptionValidationTests(_NotesFolder):
    def test_bad_options_are_refused_at_construction(self) -> None:
        # Section 8.5, row 10: smart_case must be a bool and context_lines an int in 0..GREP_MAX_CONTEXT_LINES.
        from vidbyte.tools.builtins.code_search.grep import GREP_MAX_CONTEXT_LINES

        for options in ({"smart_case": "yes"}, {"smart_case": 1}, {"smart_case": None}, {"context_lines": -1}, {"context_lines": GREP_MAX_CONTEXT_LINES + 1}, {"context_lines": True}, {"context_lines": 2.5}, {"context_lines": "2"}):
            with self.subTest(options=options):
                with self.assertRaises(ConfigurationError) as caught:
                    GrepTool(self.root, **options)
                self.assertIn(next(iter(options)), str(caught.exception) + str(getattr(caught.exception, "details", "")))
        GrepTool(self.root, smart_case=True, context_lines=GREP_MAX_CONTEXT_LINES)

    def test_each_non_default_option_adds_one_sentence_to_the_spec(self) -> None:
        # FR-3.1, section 9.4: the base sentence stays first; smart case adds a sentence about letter case, and context_lines adds the fixed sentence.
        smart = GrepTool(self.root, smart_case=True).spec().description
        self.assertTrue(smart.startswith(MAIN_DESCRIPTION + " "), smart)
        added = smart[len(MAIN_DESCRIPTION) :].strip()
        self.assertEqual(len(re.findall(r"[.!?](?:\s|$)", added)), 1, added)
        self.assertRegex(added.lower(), r"\bcase\b")
        self.assertEqual(GrepTool(self.root, context_lines=0).spec().description, f"{MAIN_DESCRIPTION} {CONTEXT_SENTENCE.format(n=0)}")
        both = GrepTool(self.root, smart_case=True, context_lines=0).spec().description
        self.assertEqual(both, f"{smart} {CONTEXT_SENTENCE.format(n=0)}")
        self.assertEqual(GrepTool(self.root, smart_case=True).spec().parameters, GrepTool(self.root).spec().parameters)

    def test_the_call_result_is_a_success_for_every_option_combination(self) -> None:
        # INV-3.1..INV-3.3: the options change matching and context only, never the status or the metadata keys.
        for options in ({}, {"smart_case": True}, {"context_lines": 0}, {"smart_case": True, "context_lines": 5}):
            with self.subTest(options=options):
                result = _grep(GrepTool(self.root, **options), pattern="plan")
                self.assertIs(result.status, ToolStatus.SUCCESS)
                self.assertEqual(set(result.metadata), {"count", "truncated"})


if __name__ == "__main__":
    unittest.main()
