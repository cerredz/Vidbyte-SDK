"""Context Protocol Header

Description:
    Implements OutputBehavior - predicates over final response text and structured output.
Purpose:
    Exposes boolean and count methods for response shape, JSON validity, Markdown fences,
    URLs, citations, refusal/hedging language, prefixes/suffixes, and structured fields.
Architecture:
    - OutputBehavior: reads probe.output and probe.structured from the parent Behavior.
    - Text predicates use deterministic stdlib parsing and conservative regexes.
    - Structured predicates resolve dot paths across mappings, objects, and list indexes.
Relations:
    Instantiated by Behavior facade and accessed via agent.behavior.output.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidbyte.evals.behavior.behavior import Behavior


class OutputBehavior:
    """Predicates over final response output for a completed agent run."""

    _CODE_BLOCK_PATTERN = re.compile(r"(?ms)(`{3,}|~{3,})([^\n`]*)\n.*?\n\1")
    _URL_PATTERN = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>)\]]+")
    _MARKDOWN_CITATION_PATTERN = re.compile(r"\[[^\]]+\]\((?:https?://|www\.)[^)\s]+\)")
    _FOOTNOTE_CITATION_PATTERN = re.compile(r"\[\^[^\]]+\]")
    _BRACKET_CITATION_PATTERN = re.compile(r"(?<!\^)\[(?:\d+|[A-Za-z][A-Za-z0-9_-]*,\s*\d{4})\]")
    _WORD_PATTERN = re.compile(r"\b\w+\b")
    _REFUSAL_PATTERNS = (
        re.compile(r"\bi\s+can(?:not|'t)\b", re.IGNORECASE),
        re.compile(r"\bi\s+am\s+unable\s+to\b", re.IGNORECASE),
        re.compile(r"\bi'm\s+unable\s+to\b", re.IGNORECASE),
        re.compile(r"\bi\s+can't\s+help\s+with\b", re.IGNORECASE),
        re.compile(r"\bi\s+won't\b", re.IGNORECASE),
    )
    _HEDGING_PATTERNS = (
        re.compile(r"\bmaybe\b", re.IGNORECASE),
        re.compile(r"\bpossibly\b", re.IGNORECASE),
        re.compile(r"\bprobably\b", re.IGNORECASE),
        re.compile(r"\bi\s+think\b", re.IGNORECASE),
        re.compile(r"\bit\s+seems\b", re.IGNORECASE),
        re.compile(r"\bappears\s+to\b", re.IGNORECASE),
        re.compile(r"\blikely\b", re.IGNORECASE),
    )

    def __init__(self, behavior: Behavior) -> None:
        # Stores a reference to the parent Behavior facade for lazy probe access.
        self._behavior = behavior

    @property
    def _output(self) -> str:
        # Returns the response output from the probe.
        return self._behavior.probe.output

    @property
    def _structured(self) -> Any:
        # Returns the structured output object from the probe.
        return self._behavior.probe.structured

    def is_empty(self, strip: bool = True) -> bool:
        # Returns True if output is empty, optionally after stripping whitespace.
        output = self._output.strip() if strip else self._output
        return output == ""

    def is_not_empty(self, strip: bool = True) -> bool:
        # Returns True if output is not empty with the same whitespace handling as is_empty.
        return not self.is_empty(strip=strip)

    def length(self, *, at_least: int | None = None, at_most: int | None = None, strip: bool = False) -> bool:
        # Returns True if character length falls within the optional inclusive bounds.
        output = self._output.strip() if strip else self._output
        return self._within(len(output), at_least=at_least, at_most=at_most)

    def line_count(self, *, at_least: int | None = None, at_most: int | None = None) -> bool:
        # Returns True if logical line count falls within the optional inclusive bounds.
        count = 0 if self._output == "" else len(self._output.splitlines())
        return self._within(count, at_least=at_least, at_most=at_most)

    def word_count(self, *, at_least: int | None = None, at_most: int | None = None) -> bool:
        # Returns True if word-token count falls within the optional inclusive bounds.
        return self._within(len(self._WORD_PATTERN.findall(self._output)), at_least=at_least, at_most=at_most)

    def is_valid_json(self) -> bool:
        # Returns True if the raw output parses successfully as JSON.
        try:
            json.loads(self._output)
        except (json.JSONDecodeError, ValueError, TypeError):
            return False
        return True

    def contains_code_block(self, language: str | None = None) -> bool:
        # Returns True if output contains a fenced code block, optionally matching language.
        return self.code_block_count(language) > 0

    def code_block_count(self, language: str | None = None, *, at_least: int | None = None, at_most: int | None = None) -> int | bool:
        # Counts fenced code blocks, or returns a bounded check when bounds are provided.
        count = len(self._matching_code_blocks(language))
        return self._count_or_within(count, at_least=at_least, at_most=at_most)

    def contains_url(self) -> bool:
        # Returns True if output contains an http, https, or www URL.
        return self.url_count() > 0

    def url_count(self, *, at_least: int | None = None, at_most: int | None = None) -> int | bool:
        # Counts detected URLs, or returns a bounded check when bounds are provided.
        count = len(self._URL_PATTERN.findall(self._output))
        return self._count_or_within(count, at_least=at_least, at_most=at_most)

    def contains_citation(self, style: str = "any") -> bool:
        # Returns True if output contains a citation-like marker for the requested style.
        return self.citation_count(style) > 0

    def citation_count(self, style: str = "any", *, at_least: int | None = None, at_most: int | None = None) -> int | bool:
        # Counts citation-like markers, or returns a bounded check when bounds are provided.
        count = self._citation_count_for_style(style)
        return self._count_or_within(count, at_least=at_least, at_most=at_most)

    def refused(self) -> bool:
        # Returns True if output contains a common refusal phrase.
        return any(pattern.search(self._output) for pattern in self._REFUSAL_PATTERNS)

    def contains_hedging(self) -> bool:
        # Returns True if output contains common hedging or uncertainty language.
        return any(pattern.search(self._output) for pattern in self._HEDGING_PATTERNS)

    def starts_with(self, prefix: str, *, case_sensitive: bool = True, strip: bool = False) -> bool:
        # Returns True if output starts with prefix under the requested normalization.
        output, target = self._normalize_pair(self._output, prefix, case_sensitive=case_sensitive, strip=strip)
        return output.startswith(target)

    def ends_with(self, suffix: str, *, case_sensitive: bool = True, strip: bool = False) -> bool:
        # Returns True if output ends with suffix under the requested normalization.
        output, target = self._normalize_pair(self._output, suffix, case_sensitive=case_sensitive, strip=strip)
        return output.endswith(target)

    def structured_valid(self) -> bool:
        # Returns True when structured output exists on the probe.
        return self._structured is not None

    def structured_field_exists(self, path: str) -> bool:
        # Returns True if the structured output contains the dot-path field.
        exists, _ = self._resolve_path(path)
        return exists

    def structured_field_equals(self, path: str, value: Any) -> bool:
        # Returns True if the resolved structured field equals value.
        exists, resolved = self._resolve_path(path)
        return exists and resolved == value

    def structured_field_matches(self, path: str, predicate: Callable[[Any], bool]) -> bool:
        # Returns True if predicate returns True for the resolved structured field.
        exists, resolved = self._resolve_path(path)
        if not exists:
            return False
        return bool(predicate(resolved))

    def structured_field_type(self, path: str, expected_type: type | tuple[type, ...]) -> bool:
        # Returns True if the resolved structured field is an instance of expected_type.
        exists, resolved = self._resolve_path(path)
        return exists and isinstance(resolved, expected_type)

    def structured_contains_keys(self, keys: Sequence[str]) -> bool:
        # Returns True if top-level structured mapping contains every requested key.
        root = self._as_mapping(self._structured)
        if root is None:
            return False
        return all(key in root for key in keys)

    def _matching_code_blocks(self, language: str | None) -> list[re.Match[str]]:
        # Returns fenced code block matches, optionally filtered by language token.
        matches = list(self._CODE_BLOCK_PATTERN.finditer(self._output))
        if language is None:
            return matches
        expected = language.casefold()
        return [match for match in matches if self._code_language(match).casefold() == expected]

    def _code_language(self, match: re.Match[str]) -> str:
        # Extracts the first language token from a fenced code block match.
        info = match.group(2).strip()
        if not info:
            return ""
        return info.split()[0]

    def _citation_count_for_style(self, style: str) -> int:
        # Counts citation-like markers for a supported citation style.
        normalized = style.casefold()
        if normalized == "markdown":
            return len(self._MARKDOWN_CITATION_PATTERN.findall(self._output))
        if normalized == "bracket":
            return len(self._BRACKET_CITATION_PATTERN.findall(self._output))
        if normalized == "footnote":
            return len(self._FOOTNOTE_CITATION_PATTERN.findall(self._output))
        if normalized == "url":
            return int(self.url_count())
        if normalized == "any":
            return (
                int(self.citation_count("markdown"))
                + int(self.citation_count("bracket"))
                + int(self.citation_count("footnote"))
                + int(self.citation_count("url"))
            )
        raise ValueError(f"Unsupported citation style: {style}")

    def _resolve_path(self, path: str) -> tuple[bool, Any]:
        # Resolves a dot path against structured output, returning (exists, value).
        if not path:
            return False, None
        current = self._structured
        if current is None:
            return False, None
        for segment in path.split("."):
            exists, current = self._resolve_segment(current, segment)
            if not exists:
                return False, None
        return True, current

    def _resolve_segment(self, current: Any, segment: str) -> tuple[bool, Any]:
        # Resolves one path segment against a mapping, sequence, or object attribute.
        mapping = self._as_mapping(current)
        if mapping is not None:
            if segment in mapping:
                return True, mapping[segment]
            return False, None
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            if not segment.isdigit():
                return False, None
            index = int(segment)
            if index >= len(current):
                return False, None
            return True, current[index]
        if hasattr(current, segment):
            return True, getattr(current, segment)
        return False, None

    def _as_mapping(self, value: Any) -> Mapping[str, Any] | None:
        # Coerces mapping-like structured objects into mappings when possible.
        if isinstance(value, Mapping):
            return value
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, Mapping):
                return dumped
        return None

    def _normalize_pair(self, output: str, target: str, *, case_sensitive: bool, strip: bool) -> tuple[str, str]:
        # Applies whitespace and case normalization to output and comparison target.
        if strip:
            output = output.strip()
            target = target.strip()
        if not case_sensitive:
            output = output.casefold()
            target = target.casefold()
        return output, target

    def _count_or_within(self, count: int, *, at_least: int | None, at_most: int | None) -> int | bool:
        # Returns raw count with no bounds, otherwise returns an inclusive bounded check.
        if at_least is None and at_most is None:
            return count
        return self._within(count, at_least=at_least, at_most=at_most)

    def _within(self, value: int, *, at_least: int | None, at_most: int | None) -> bool:
        # Returns True if value falls within the optional inclusive bounds.
        if at_least is not None and value < at_least:
            return False
        if at_most is not None and value > at_most:
            return False
        return True


__all__ = ["OutputBehavior"]
