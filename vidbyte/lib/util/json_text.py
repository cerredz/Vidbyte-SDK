"""FILE: vidbyte/lib/util/json_text.py

PURPOSE:
    Decodes the one JSON object a model answer holds: whitespace and one
    surrounding Markdown code fence are removed, and what is left must be
    exactly one JSON object, returned as a read-only mapping. Anything else
    raises ValueError; there is never a fallback value.

ROLE IN CODEBASE:
    The canonical decoder for JSON-from-model-text. Called by
    JsonAnswers.parse_json_answer in vidbyte/harnesses/native/compose/
    answers.py, which turns a ValueError into a repair turn. Re-exported from
    vidbyte/lib/util/__init__.py. Uses only the standard library.

ARCHITECTURE NOTE:
    A static-method-only class with no SDK dependencies, like
    SubstringCounter in text.py. json.JSONDecodeError is already a ValueError;
    a RecursionError from very deep nesting is turned into one, so a caller
    handles exactly one exception type for a bad answer.

FUNCTION INVENTORY:
    JsonText.decode(text) -> Mapping[str, object]: the read-only object.
    JsonText._unfenced(text) -> str: the inside of one surrounding fence, or
    the text unchanged.

COMMON MODIFICATION PATTERNS:
    A new tolerated wrapping (another fence language) is one more entry in
    JSON_FENCE_LANGUAGES; keep every other shape a ValueError.

WHAT NOT TO DO IN THIS FILE:
    1. Do not import any SDK module.
    2. Do not search the text for the first brace or repair the JSON; an
       answer with prose around it is refused so the model is asked again.
    3. Do not return an empty mapping or None instead of raising.

KNOWN EDGE CASES:
    A fenced answer must put the opening fence on its own line. Two nested
    fences leave one fence inside, which is not JSON and is refused. Only the
    top-level mapping is read-only; nested objects stay plain dicts.

RELATED DOCS:
    vidbyte/harnesses/README.md

TESTS:
    tests/features/harness_compose/test_harness_compose_answers.py
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from types import MappingProxyType

JSON_FENCE = "```"
JSON_FENCE_LANGUAGES = frozenset({"", "json"})
# The JSON name of each value kind json.loads returns, for messages.
JSON_KIND_NAMES: MappingProxyType[type, str] = MappingProxyType({list: "array", str: "string", int: "number", float: "number", bool: "boolean", type(None): "null"})


class JsonText:
    """Strict decoding of the single JSON object in a model answer."""

    @staticmethod
    def decode(text: str) -> Mapping[str, object]:
        """Return the JSON object text holds as a read-only mapping, or raise ValueError."""
        # @intent model-json-answers-decode-strictly-or-fail
        # Remove the whitespace around the answer and one surrounding
        # code fence, then require exactly one JSON object; anything
        # else, including nesting too deep to parse, is a ValueError.
        if not isinstance(text, str):
            raise ValueError(f"The answer must be text; got a value of type {type(text).__name__}.")
        body = JsonText._unfenced(text.strip())
        try:
            value = json.loads(body)
        except RecursionError:
            raise ValueError("The answer nests JSON too deeply to read.") from None
        if not isinstance(value, dict):
            raise ValueError(f"The answer must be one JSON object; it is a JSON {JSON_KIND_NAMES[type(value)]}.")
        return MappingProxyType(value)

    @staticmethod
    def _unfenced(text: str) -> str:
        # The inside of one fence whose opening line is ``` or ```json,
        # or the text unchanged when it is not wrapped in one.
        opener, newline, rest = text.partition("\n")
        language = opener.removeprefix(JSON_FENCE).strip().lower()
        if not newline or not opener.startswith(JSON_FENCE) or not text.endswith(JSON_FENCE) or language not in JSON_FENCE_LANGUAGES:
            return text
        return rest.removesuffix(JSON_FENCE).strip()


__all__ = ["JsonText"]
