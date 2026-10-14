"""FILE: vidbyte/tools/builtins/prebuilt/regex.py

PURPOSE: Defines RegexToolFunctions, the seven prebuilt regular-expression tools: finding every match, matching a whole text, its start, or anywhere in it, replacing with a template, splitting, checking that a pattern compiles, testing a pattern against good and bad samples, and filtering names with a shell-style wildcard.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the REGEX category is chosen. Builds on PrebuiltToolSupport in _support.py for the item cap, the character budget, and the argument error, and on the RegexFlag and RegexMatchMode enums.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Patterns compile with the standard re module through one helper that turns a compile failure into an argument error built from re.error.msg and re.error.pos. Matches are walked lazily with finditer, so totals are counted without building every item, and the two INV-20 tools measure their output while they read it.
FUNCTION INVENTORY: regex_find_all, regex_match, regex_replace, regex_split, verify_regex_pattern, regex_test_samples, and wildcard_match_names are the tools; _compile combines the flags and compiles a pattern; _matcher picks the match method for a RegexMatchMode; _match_values reads one match's groups under the output cap; _replace_measured rebuilds a text with replacements under the output cap; _split_parts yields the parts of a split lazily; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new regex tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.15, and its entry in tool_functions. A new RegexFlag member adds its re flag to _FLAG_VALUES, and a new RegexMatchMode member adds a case to _matcher.
WHAT NOT TO DO IN THIS FILE: 1. Do not put str(exc) of an re.error in a message or an output; read its msg and pos attributes. 2. Do not call re.split, findall, or sub on the whole text when groups can copy the rest of the text; walk finditer so the item cap and the character budget stop the work. 3. Do not add a timeout or a worker; catastrophic backtracking is an accepted limitation (EC-10). 4. Do not lowercase a text before a positional search; the ignore_case flag keeps positions on the original text.
KNOWN EDGE CASES: A pattern that nests groups very deeply raises RecursionError and a huge repeat count raises OverflowError instead of re.error, so both are reported as compile failures without a position. An unknown group name in a replacement template raises IndexError inside the re module on Python 3.11. A template is checked against an empty text first, so a bad template fails even when nothing matches. Empty matches next to a previous match follow the re module's own rules, so finditer, the split parts, and the replacements agree with re.split and re.sub.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.15, section 9.2 items 6, 12, and 13, EC-10); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_unicode_regex.py, tests/features/prebuilt_tools/test_prebuilt_resource_bounds.py, and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable, Iterator
from functools import reduce
from itertools import islice
from operator import or_
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_PATTERN_CHARS,
    PREBUILT_MAX_REGEX_SAMPLES,
    PREBUILT_MAX_REGEX_TEXT_CHARS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import RegexFlag, RegexMatchMode
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_MAX_FLAGS = len(RegexFlag)
_MESSAGE_PREVIEW_LENGTH = 80
_FLAG_VALUES = MappingProxyType(
    {
        RegexFlag.IGNORE_CASE: re.IGNORECASE,
        RegexFlag.MULTILINE: re.MULTILINE,
        RegexFlag.DOT_ALL: re.DOTALL,
        RegexFlag.VERBOSE: re.VERBOSE,
        RegexFlag.ASCII: re.ASCII,
    }
)
_VALID_PATTERN = "a valid Python regular expression of the re module"
_TOO_LARGE_PATTERN = "a repetition count is too large or the groups nest too deeply to compile"
_OVER_OUTPUT_CAP = f"the result would hold more than {PREBUILT_MAX_TEXT_CHARS} characters"

_PATTERN_DESCRIPTION = "The regular expression to apply, written in the syntax of the Python re module. It must hold at least one character and at most one thousand. A pattern that does not compile fails with an error naming pattern that gives the compiler's message and position. A pattern prone to catastrophic backtracking can run for a very long time, so keep repeated parts simple."
_TEXT_DESCRIPTION = "The text to search, given as plain characters. Positions count Unicode code points, so an emoji or an accented letter counts once. The text may be empty and may hold at most one hundred thousand characters. Line breaks are ordinary characters unless the multiline or dot_all flag changes how anchors and the dot treat them."
_FLAGS_DESCRIPTION = "Regular expression flags to apply, each given by its lowercase name. The ignore_case flag folds case, multiline lets the line anchors match at every line, dot_all lets the dot match a line break, verbose allows whitespace and comments in the pattern, and ascii limits the word, digit, and space classes to ASCII. The default is no flags. At most five flags may be given, and a repeated flag has no further effect."
_MODE_DESCRIPTION = "How much of the text the pattern must match. The full mode requires the whole text to match, prefix requires a match that starts at the first character, and search accepts a match anywhere. The default is full. Any other value fails validation."


class RegexToolFunctions:
    """The regex category: matching, replacing, splitting, and checking regular expressions, plus wildcard filtering."""

    @staticmethod
    def regex_find_all(
        pattern: Annotated[str, Field(description=_PATTERN_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_PATTERN_CHARS)],
        text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_REGEX_TEXT_CHARS)],
        flags: Annotated[tuple[RegexFlag, ...], Field(description=_FLAGS_DESCRIPTION, max_length=_MAX_FLAGS)] = (),
    ) -> PrebuiltToolOutput:
        """List every non-overlapping match of a regular expression in a text, with each match's text, 0-based start and end positions, numbered groups, and named groups. Use it to pull every occurrence of a pattern out of a text instead of scanning by eye. Groups that took no part in a match are null, positions count Unicode code points, and at most 1,000 matches are listed while count covers every match. A pattern that does not compile fails with an error naming pattern, and a catastrophic pattern can run for a very long time."""
        # Compile once, then count every match without building any.
        compiled = RegexToolFunctions._compile(pattern, flags)
        count = sum(1 for _ in compiled.finditer(text))

        # Build match entries lazily so the item cap and the character
        # budget stop the walk early.
        entries = (
            {"match": found.group(), "start": found.start(), "end": found.end(), "groups": list(found.groups()), "named_groups": found.groupdict()}
            for found in compiled.finditer(text)
        )
        matches, truncated = PrebuiltToolSupport.cap_items(entries)
        return {"count": count, "matches": matches, "truncated": truncated}

    @staticmethod
    def regex_match(
        pattern: Annotated[str, Field(description=_PATTERN_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_PATTERN_CHARS)],
        text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_REGEX_TEXT_CHARS)],
        flags: Annotated[tuple[RegexFlag, ...], Field(description=_FLAGS_DESCRIPTION, max_length=_MAX_FLAGS)] = (),
        mode: Annotated[RegexMatchMode, Field(description=_MODE_DESCRIPTION)] = RegexMatchMode.FULL,
    ) -> PrebuiltToolOutput:
        """Test whether a regular expression matches a whole text, the start of a text, or anywhere in it, and report the match with its positions and groups. Use it to check that a value has an expected format or to read the parts of one match. The mode chooses full, prefix, or search matching, groups that took no part are null, and with no match every value is null and both group collections are empty. A pattern that does not compile, or a match whose text and group values together pass one million characters, fails with an error naming pattern."""
        # Compile the pattern and run the match method the mode picks.
        compiled = RegexToolFunctions._compile(pattern, flags)
        found = RegexToolFunctions._matcher(compiled, mode)(text)
        if found is None:
            return {"matched": False, "match": None, "start": None, "end": None, "groups": [], "named_groups": {}}

        # Read the groups one at a time under the output cap.
        groups, named_groups = RegexToolFunctions._match_values(found)
        return {"matched": True, "match": found.group(), "start": found.start(), "end": found.end(), "groups": groups, "named_groups": named_groups}

    @staticmethod
    def regex_replace(
        pattern: Annotated[str, Field(description=_PATTERN_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_PATTERN_CHARS)],
        replacement: Annotated[str, Field(description="The replacement template, written in the syntax of the Python re module. A backslash followed by a group number inserts that numbered group, and a backslash with g and a group name or number in angle brackets inserts that group. Backslash escapes for line breaks and tabs are honored, and a group that took no part in a match inserts nothing. A template that refers to a missing group fails with an error naming replacement. It may hold at most ten thousand characters.", max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_REGEX_TEXT_CHARS)],
        flags: Annotated[tuple[RegexFlag, ...], Field(description=_FLAGS_DESCRIPTION, max_length=_MAX_FLAGS)] = (),
        max_replacements: Annotated[int | None, Field(description="The largest number of matches to replace, counted from the start of the text. Matches after that many replacements are left unchanged. Null, the default, replaces every match. The value must be at least 1.", ge=1)] = None,
    ) -> PrebuiltToolOutput:
        """Replace the matches of a regular expression in a text with a replacement template and report how many replacements were made. Use it for pattern-based edits across a whole text, like reordering captured parts or unifying separators. The template refers to numbered groups with a backslash and a number and to named groups with a backslash, g, and the name in angle brackets, and max_replacements limits how many matches are replaced from the left. A pattern that does not compile fails naming pattern, while a bad template or a result over one million characters fails naming replacement."""
        # Compile the pattern, then check the template against empty
        # text so a bad template fails even when nothing matches.
        compiled = RegexToolFunctions._compile(pattern, flags)
        try:
            compiled.sub(replacement, "")
        except re.error as exc:
            message = exc.msg[:_MESSAGE_PREVIEW_LENGTH]
            raise PrebuiltToolSupport.argument_error("replacement", f"the template is invalid at position {exc.pos}: {message}", "a template whose group references all exist in the pattern") from exc
        except IndexError as exc:
            raise PrebuiltToolSupport.argument_error("replacement", "the template names a group the pattern does not define", "a template whose group names all exist in the pattern") from exc

        # Rebuild the text, refusing a result over the output cap.
        rebuilt, replacements = RegexToolFunctions._replace_measured(compiled, replacement, text, max_replacements)
        return {"text": rebuilt, "replacements": replacements}

    @staticmethod
    def regex_split(
        pattern: Annotated[str, Field(description=_PATTERN_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_PATTERN_CHARS)],
        text: Annotated[str, Field(description=_TEXT_DESCRIPTION, max_length=PREBUILT_MAX_REGEX_TEXT_CHARS)],
        flags: Annotated[tuple[RegexFlag, ...], Field(description=_FLAGS_DESCRIPTION, max_length=_MAX_FLAGS)] = (),
        max_splits: Annotated[int | None, Field(description="The largest number of splits to make, counted from the start of the text. The rest of the text after that many splits stays in the last part. Null, the default, splits at every match. The value must be at least 1.", ge=1)] = None,
    ) -> PrebuiltToolOutput:
        """Split a text at every match of a regular expression and return the parts in order. Use it to break a text on a separator pattern that a plain string split cannot express. Captured groups in the pattern appear among the parts, a group that took no part is null, and max_splits limits how many splits are made from the left. At most 1,000 parts are listed while count covers every part, and a pattern that does not compile fails with an error naming pattern."""
        # Count the splits, which fixes the number of parts: one more
        # than the splits, plus one part for each group at each split.
        compiled = RegexToolFunctions._compile(pattern, flags)
        splits = sum(1 for _ in islice(compiled.finditer(text), max_splits))
        count = splits * (compiled.groups + 1) + 1

        # List the parts lazily so the item cap and budget stop early.
        parts, truncated = PrebuiltToolSupport.cap_items(RegexToolFunctions._split_parts(compiled, text, max_splits))
        return {"parts": parts, "count": count, "truncated": truncated}

    @staticmethod
    def verify_regex_pattern(
        pattern: Annotated[str, Field(description="The regular expression to check, written in the syntax of the Python re module. It must hold at least one character and at most one thousand. A pattern that does not compile gives a result with valid set to false rather than an error. The flags can change whether a pattern compiles, so pass the ones it will be used with.", min_length=1, max_length=PREBUILT_MAX_PATTERN_CHARS)],
        flags: Annotated[tuple[RegexFlag, ...], Field(description=_FLAGS_DESCRIPTION, max_length=_MAX_FLAGS)] = (),
    ) -> PrebuiltToolOutput:
        """Check whether a regular expression compiles with the Python re module and the given flags, and report its group count and group names or the compiler's error. Use it before running a pattern that might be malformed, or to find out why a pattern fails elsewhere. An invalid pattern is a successful result with valid set to false, the compiler's message, and the 0-based position in the pattern where it failed. Group names are listed in group order, and the tool has no failure case beyond its length caps."""
        # Compile with the combined flags; a failure is a result, and
        # its message and position come from the error's attributes.
        try:
            compiled = re.compile(pattern, reduce(or_, (_FLAG_VALUES[flag] for flag in flags), re.NOFLAG))
        except re.error as exc:
            return {"valid": False, "error": exc.msg, "error_position": exc.pos, "group_count": 0, "group_names": []}
        except (OverflowError, RecursionError):
            return {"valid": False, "error": _TOO_LARGE_PATTERN, "error_position": None, "group_count": 0, "group_names": []}

        # List the group names in the order of their group numbers.
        names = [name for name, _ in sorted(compiled.groupindex.items(), key=lambda item: item[1])]
        return {"valid": True, "error": None, "error_position": None, "group_count": compiled.groups, "group_names": names}

    @staticmethod
    def regex_test_samples(
        pattern: Annotated[str, Field(description=_PATTERN_DESCRIPTION, min_length=1, max_length=PREBUILT_MAX_PATTERN_CHARS)],
        should_match: Annotated[
            list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]],
            Field(description="Samples the pattern is expected to match under the chosen mode. Each sample may hold at most ten thousand characters, and the list may hold at most one hundred samples. A sample that does not match is reported as a failure with expected_match set to true. This list and should_not_match may not both be empty.", max_length=PREBUILT_MAX_REGEX_SAMPLES),
        ],
        should_not_match: Annotated[
            tuple[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)], ...],
            Field(description="Samples the pattern is expected not to match under the chosen mode. Each sample may hold at most ten thousand characters, and the list may hold at most one hundred samples. A sample that matches is reported as a failure with expected_match set to false. The default is an empty list.", max_length=PREBUILT_MAX_REGEX_SAMPLES),
        ] = (),
        flags: Annotated[tuple[RegexFlag, ...], Field(description=_FLAGS_DESCRIPTION, max_length=_MAX_FLAGS)] = (),
        mode: Annotated[RegexMatchMode, Field(description=_MODE_DESCRIPTION)] = RegexMatchMode.FULL,
    ) -> PrebuiltToolOutput:
        """Test a regular expression against samples that should match and samples that should not, and report how many passed and which failed. Use it to verify a pattern against known good and bad inputs before relying on it. The mode chooses full, prefix, or search matching, and failures are listed in input order with the should-match samples first. Both sample lists empty fails with an error naming should_match, and a pattern that does not compile fails naming pattern."""
        # Refuse a call with nothing to test, then compile the pattern.
        if not should_match and not should_not_match:
            raise PrebuiltToolSupport.argument_error("should_match", "both sample lists are empty", "at least one sample in should_match or should_not_match")
        test = RegexToolFunctions._matcher(RegexToolFunctions._compile(pattern, flags), mode)

        # Record every sample whose outcome differs from the expected
        # one, should-match samples first.
        expectations = [(sample, True) for sample in should_match] + [(sample, False) for sample in should_not_match]
        failures = [{"sample": sample, "expected_match": expected} for sample, expected in expectations if (test(sample) is not None) != expected]
        return {"all_passed": not failures, "passed": len(expectations) - len(failures), "failed": len(failures), "failures": failures}

    @staticmethod
    def wildcard_match_names(
        pattern: Annotated[str, Field(description="The shell-style wildcard pattern each whole name is matched against. A star matches any run of characters, a question mark matches exactly one character, and square brackets match one character from a set or, after an exclamation mark, one character outside it. Every other character matches only itself. The pattern must hold at least one character and at most one thousand.", min_length=1, max_length=PREBUILT_MAX_PATTERN_CHARS)],
        names: Annotated[
            list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]],
            Field(description="The names to filter, which keep their input order in the result. Each name is matched as a whole against the pattern, and a slash is an ordinary character. Each name may hold at most ten thousand characters. The list may hold at most ten thousand names.", max_length=PREBUILT_MAX_LIST_ITEMS),
        ],
        case_sensitive: Annotated[bool, Field(description="Whether uppercase and lowercase must match exactly. When false, the pattern and each name are lowercased before matching, and the result keeps each name's original spelling. The default is true. Character ranges in brackets are lowercased along with the rest of the pattern.")] = True,
    ) -> PrebuiltToolOutput:
        """Filter a list of names with a shell-style wildcard pattern and return the names that match, in their input order. Use it to select file names or identifiers by a glob pattern instead of writing a regular expression. A star matches any run of characters, slashes included, a question mark matches one character, and square brackets match one character from a set, with a leading exclamation mark negating it. Matching is case-sensitive unless case_sensitive is false, and at most 1,000 matches are listed while count covers every match."""
        # Lowercase both sides when case does not matter, then keep the
        # matching names in input order.
        wanted = pattern if case_sensitive else pattern.lower()
        matched = [name for name in names if fnmatch.fnmatchcase(name if case_sensitive else name.lower(), wanted)]
        kept, truncated = PrebuiltToolSupport.cap_items(matched)
        return {"matches": kept, "count": len(matched), "truncated": truncated}

    @staticmethod
    def _compile(pattern: str, flags: tuple[RegexFlag, ...]) -> re.Pattern[str]:
        """Compile a pattern with the combined flags, turning a compile failure into an error naming pattern."""
        try:
            return re.compile(pattern, reduce(or_, (_FLAG_VALUES[flag] for flag in flags), re.NOFLAG))
        except re.error as exc:
            message = exc.msg[:_MESSAGE_PREVIEW_LENGTH]
            raise PrebuiltToolSupport.argument_error("pattern", f"the pattern does not compile at position {exc.pos}: {message}", _VALID_PATTERN) from exc
        except (OverflowError, RecursionError) as exc:
            raise PrebuiltToolSupport.argument_error("pattern", _TOO_LARGE_PATTERN, _VALID_PATTERN) from exc

    @staticmethod
    def _matcher(compiled: re.Pattern[str], mode: RegexMatchMode) -> Callable[[str], re.Match[str] | None]:
        """Return the match method of a compiled pattern that a RegexMatchMode names."""
        match mode:
            case RegexMatchMode.PREFIX:
                return compiled.match
            case RegexMatchMode.SEARCH:
                return compiled.search
            case _:
                return compiled.fullmatch

    @staticmethod
    def _match_values(found: re.Match[str]) -> tuple[list[str | None], dict[str, str | None]]:
        """Read a match's numbered and named group values one at a time, refusing them once they pass the output cap."""
        used = len(found.group())
        groups: list[str | None] = []
        named: dict[str, str | None] = {}
        reads: list[tuple[str | None, int]] = [(None, index) for index in range(1, found.re.groups + 1)]
        reads.extend(found.re.groupindex.items())
        for name, index in reads:
            value = found.group(index)
            used += len(value) if value is not None else 0
            # @intent prebuilt-regex-match-output-cap
            # Lookahead groups can each copy the rest of the text, so
            # the values are measured as they are read and refused as
            # soon as they pass the output cap, before any more exist.
            if used > PREBUILT_MAX_TEXT_CHARS:
                raise PrebuiltToolSupport.argument_error("pattern", f"the match and its group values would hold more than {PREBUILT_MAX_TEXT_CHARS} characters", "a pattern whose match and groups stay within that size")
            if name is None:
                groups.append(value)
            else:
                named[name] = value
        return groups, named

    @staticmethod
    def _replace_measured(compiled: re.Pattern[str], replacement: str, text: str, max_replacements: int | None) -> tuple[str, int]:
        """Rebuild a text with each match replaced by its expanded template, refusing a result over the output cap."""
        # A template without a backslash is used as it is, which is how
        # the re module treats it too.
        literal = None if "\\" in replacement else replacement
        pieces: list[str] = []
        size = 0
        last = 0
        replacements = 0
        for found in islice(compiled.finditer(text), max_replacements):
            expanded = literal if literal is not None else found.expand(replacement)
            size += found.start() - last + len(expanded)
            # @intent prebuilt-regex-replace-output-cap
            # A short template repeated at every match can multiply the
            # text, so the result is measured while it is built and
            # refused as soon as it would pass the output cap.
            if size > PREBUILT_MAX_TEXT_CHARS:
                raise PrebuiltToolSupport.argument_error("replacement", _OVER_OUTPUT_CAP, f"a pattern and replacement whose result has at most {PREBUILT_MAX_TEXT_CHARS} characters")
            pieces.append(text[last : found.start()])
            pieces.append(expanded)
            last = found.end()
            replacements += 1
        if size + len(text) - last > PREBUILT_MAX_TEXT_CHARS:
            raise PrebuiltToolSupport.argument_error("replacement", _OVER_OUTPUT_CAP, f"a pattern and replacement whose result has at most {PREBUILT_MAX_TEXT_CHARS} characters")
        pieces.append(text[last:])
        return "".join(pieces), replacements

    @staticmethod
    def _split_parts(compiled: re.Pattern[str], text: str, max_splits: int | None) -> Iterator[str | None]:
        """Yield the parts re.split would return, one at a time: the text before each split, then each group of that split."""
        last = 0
        for found in islice(compiled.finditer(text), max_splits):
            yield text[last : found.start()]
            for index in range(1, compiled.groups + 1):
                yield found.group(index)
            last = found.end()
        yield text[last:]

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.regex_find_all,
            cls.regex_match,
            cls.regex_replace,
            cls.regex_split,
            cls.verify_regex_pattern,
            cls.regex_test_samples,
            cls.wildcard_match_names,
        )


__all__ = ["RegexToolFunctions"]
