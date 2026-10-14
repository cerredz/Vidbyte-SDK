"""FILE: vidbyte/tools/builtins/prebuilt/json_data.py

PURPOSE: Defines JsonDataToolFunctions, the nine prebuilt tools that work on JSON documents: checking syntax, formatting, reading and setting a value at a JSON Pointer, listing every path, diffing two documents, applying a JSON Patch, summarizing the shape of a document, and pulling JSON out of surrounding text.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the JSON_DATA category is chosen. Builds on PrebuiltToolSupport in _support.py for JSON parsing under the nesting cap, JSON Pointer splitting, nesting measurement, the item cap, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Documents are walked with explicit work stacks instead of recursion, and pointer text is written only for the items a result keeps, so a long key is never copied once for every value below it. A document being edited sits in a one-member holder object, so even the root has a parent and every edit changes one member or one item.
FUNCTION INVENTORY: verify_json_syntax, format_json, json_get_value, json_set_value, list_json_paths, diff_json_documents, apply_json_patch, summarize_json_structure, and extract_json_from_text are the tools. _formatted_length predicts formatted output length; _lookup reads a pointer target; _parent_slot, _slot_value, and _slot_insert find, read, and change one member or item; _patch_operations, _operation_fields, and _measured_insertion read JSON Patch operations and account for their size; _same_json compares values type-aware; _path_steps and _path_entry list paths; _change_steps and _change_entry list differences; _value_count and _merged_shape describe structure; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new JSON tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.17, and its entry in tool_functions. A new pointer-based edit reuses _parent_slot and _slot_insert from the tool itself rather than from another helper.
WHAT NOT TO DO IN THIS FILE: 1. Do not recurse over a document; use a work stack, as every walk here does. 2. Do not write pointer text for every value up front, because a long key would be copied once per value below it. 3. Do not call json.dumps on an edited document before its nesting is known to be within the cap, because json.dumps recurses and its RecursionError would escape as the wrong error type. 4. Do not compare JSON values with == alone, which treats true as 1; use _same_json. 5. Do not iterate a set or a hash-ordered container when building an output.
KNOWN EDGE CASES: An integer literal of more than 4,300 digits is valid JSON that Python refuses to read, so verify_json_syntax reports it as invalid with a fixed message. A move to its own path takes the value out and puts it back, so an object member moves to the end of its object. When merged shapes give two keys the same label, such as a key ending in a question mark next to an optional key of the same stem, the later one wins. An array index of more than nine digits can never point into a list a document of one million characters holds, so it is treated as past the end.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.17, section 9.2 items 3, 12, 13, and 14); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_json_csv.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Collection, Iterator
from functools import partial
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_INDENT,
    PREBUILT_MAX_JSON_NESTING,
    PREBUILT_MAX_JSON_SCAN_STARTS,
    PREBUILT_MAX_MEDIUM_TEXT_CHARS,
    PREBUILT_MAX_PATCH_OPERATIONS,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
    PREBUILT_MAX_TEXT_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import JsonChangeKind, JsonType
from vidbyte.lib.errors import ToolExecutionError
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_COMPACT_SEPARATORS = (",", ":")
_ABSENT = object()
_ARRAY_INDEX = re.compile(r"0|[1-9][0-9]{0,8}")
_BAD_POINTER = re.compile(r"\A[^/]|~(?![01])")
_OPENING_BRACKET = re.compile(r"[\[{]")
_JSON_TYPES = MappingProxyType({dict: JsonType.OBJECT, list: JsonType.ARRAY, str: JsonType.STRING, bool: JsonType.BOOLEAN, int: JsonType.NUMBER, float: JsonType.NUMBER, type(None): JsonType.NULL})
_PATCH_POINTERS = MappingProxyType({"add": ("path",), "remove": ("path",), "replace": ("path",), "move": ("from", "path"), "copy": ("from", "path"), "test": ("path",)})
_VALUE_OPERATIONS = frozenset({"add", "replace", "test"})
_TAKING_OPERATIONS = frozenset({"remove", "move"})
_INSERTING_OPERATIONS = frozenset({"add", "replace", "copy"})
_REMOVING_OPERATIONS = frozenset({"remove", "replace"})
_TOO_DEEP_MESSAGE = f"the JSON is nested deeper than {PREBUILT_MAX_JSON_NESTING} levels of arrays and objects"
_CONSTANT_MESSAGE = "the JSON contains NaN, Infinity, or -Infinity, which are not valid JSON numbers"
_LONG_INTEGER_MESSAGE = "the JSON contains an integer with more digits than the parser accepts"
_PATCH_EXPECTED = "an array of RFC 6902 operations whose paths exist and whose tests pass"

_JSON_TEXT_PARAMETER_DESCRIPTION = "The text of one JSON document, given as a string rather than as a JSON value. When an object repeats a key, the last value wins. The constants NaN, Infinity, and -Infinity are refused, and nesting may reach at most 100 levels of arrays and objects. The text may hold at most one million characters."
_POINTER_PARAMETER_DESCRIPTION = "A JSON Pointer under RFC 6901 that names one value in the document. The empty pointer names the whole document, and any other pointer starts with a slash before each object key or array index. Inside a key, a tilde is written as ~0 and a slash as ~1. Array indexes are decimal numbers without leading zeros, and the dash means the position after the last item."


class JsonDataToolFunctions:
    """The json_data category: checking, formatting, reading, editing, comparing, and finding JSON documents."""

    @staticmethod
    def verify_json_syntax(json_text: Annotated[str, Field(description="The text to check as JSON, given as a plain string. It may be empty, which is reported as invalid. Line and column numbers in the result start at 1, and the position counts code points from 0. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Check whether a text is valid JSON and, when it is not, report the parser's message with the line, column, and 0-based position where parsing stopped. Use it before handing JSON to another tool or system, or to find the exact spot where a hand-written document breaks. The constants NaN, Infinity, and -Infinity count as invalid, and so does nesting deeper than 100 levels, both with a fixed message and null positions. Invalid JSON is a normal result with valid set to false, so the tool fails only when the text is over its length cap."""
        # Parse the text, noting any non-finite constant instead of
        # accepting it; a syntax error is reported where it happened.
        constants: list[str] = []
        problem: str | None = None
        value: object = None
        try:
            value = json.loads(json_text, parse_constant=constants.append)
        except json.JSONDecodeError as exc:
            return {"valid": False, "error": exc.msg, "line": exc.lineno, "column": exc.colno, "position": exc.pos, "top_level_type": None}
        except RecursionError:
            problem = _TOO_DEEP_MESSAGE
        except ValueError:
            problem = _LONG_INTEGER_MESSAGE

        # Non-finite constants and nesting past the cap make otherwise
        # readable text invalid, with a fixed message and no position.
        if problem is None and constants:
            problem = _CONSTANT_MESSAGE
        if problem is None and PrebuiltToolSupport.nesting_level(value) > PREBUILT_MAX_JSON_NESTING:
            problem = _TOO_DEEP_MESSAGE
        if problem is not None:
            return {"valid": False, "error": problem, "line": None, "column": None, "position": None, "top_level_type": None}
        return {"valid": True, "error": None, "line": None, "column": None, "position": None, "top_level_type": _JSON_TYPES[type(value)].value}

    @staticmethod
    def format_json(
        json_text: Annotated[str, Field(description=_JSON_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        indent: Annotated[int, Field(description="How many spaces to indent each nesting level of the output. Zero gives compact output with no spaces or line breaks at all. Any other value puts every array item and object member on its own line, with a space after each colon. The value must be between 0 and 8.", ge=0, le=PREBUILT_MAX_INDENT)] = 2,
        sort_keys: Annotated[bool, Field(description="Whether to sort the members of every object by key. When false, members keep the order they have in the input. Sorting compares keys by code point. The default is false.")] = False,
        ensure_ascii: Annotated[bool, Field(description="Whether to escape every non-ASCII character in the output. When true, such characters are written as backslash-u escapes, which can make the text several times longer. When false, they are written as themselves. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Rewrite a JSON document as indented, readable text or as compact text with no spaces, optionally sorting object keys. Use it to make JSON easier to read, to minify it, or to give two documents the same layout before comparing them. An indent of 0 gives compact output, any other indent puts each item on its own line, and ensure_ascii escapes every non-ASCII character. Invalid JSON fails naming json_text, and output that would pass one million characters fails naming indent before it is built."""
        document = PrebuiltToolSupport.parse_json_text(json_text, "json_text")

        # @intent prebuilt-output-text-cap
        # Indentation can multiply a document's size, so the formatted
        # length is predicted from the parsed document and an oversized
        # result is refused before any of it is built.
        predicted = JsonDataToolFunctions._formatted_length(document, indent, ensure_ascii)
        if predicted > PREBUILT_MAX_TEXT_CHARS:
            problem = f"the formatted JSON would have {predicted} characters, more than {PREBUILT_MAX_TEXT_CHARS}"
            raise PrebuiltToolSupport.argument_error("indent", problem, "a smaller indent, or a document whose formatted text fits the cap")

        # Write the document with the chosen layout.
        if indent == 0:
            text = json.dumps(document, separators=_COMPACT_SEPARATORS, sort_keys=sort_keys, ensure_ascii=ensure_ascii)
        else:
            text = json.dumps(document, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii)
        return {"json": text}

    @staticmethod
    def json_get_value(
        json_text: Annotated[str, Field(description=_JSON_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        pointer: Annotated[str, Field(description=_POINTER_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Read the value at a JSON Pointer path inside a JSON document and report it with its JSON type. Use it to pull one field or array item out of a large document without reading the whole document. A path that does not exist gives found false with a null value and type, and the dash index never resolves. Invalid JSON fails naming json_text, and pointer syntax errors such as a missing leading slash or a bad tilde escape fail naming pointer."""
        document = PrebuiltToolSupport.parse_json_text(json_text, "json_text")
        segments = PrebuiltToolSupport.json_pointer_tokens(pointer, "pointer")
        found, value = JsonDataToolFunctions._lookup(document, segments)
        if not found:
            return {"found": False, "value": None, "type": None}
        return {"found": True, "value": value, "type": _JSON_TYPES[type(value)].value}

    @staticmethod
    def json_set_value(
        json_text: Annotated[str, Field(description=_JSON_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        pointer: Annotated[str, Field(description=_POINTER_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)],
        value_json: Annotated[str, Field(description="The new value, given as the text of one JSON document. It may be any JSON value, including an object, an array, a string, or null. It is parsed with the same rules as json_text, so NaN and Infinity are refused. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        create_missing: Annotated[bool, Field(description="Whether to create missing parent objects along the pointer. When true, each missing object member on the way becomes an empty object, but arrays are never created. When false, a missing parent fails with an error naming pointer. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Set or insert a value at a JSON Pointer path and return the updated document as compact JSON, with whether a value was replaced. Use it to change one field or array item exactly, without rewriting the rest of the document by hand. On an array, an existing index is replaced in place while the dash or an index equal to the length appends, and the empty pointer replaces the whole document. A missing parent fails naming pointer unless create_missing is true, and a path through a scalar or past the end of an array also fails naming pointer."""
        # Read the document into a one-member holder so even the root
        # has a parent, then read the pointer and the new value.
        holder: dict[str, object] = {"": PrebuiltToolSupport.parse_json_text(json_text, "json_text")}
        segments = ["", *PrebuiltToolSupport.json_pointer_tokens(pointer, "pointer")]
        value = PrebuiltToolSupport.parse_json_text(value_json, "value_json")

        # @intent prebuilt-json-nesting-cap
        # Every segment of the pointer adds one container above the new
        # value, so a long pointer or a deep value could nest the result
        # past the cap that keeps json.dumps from recursing too far.
        nesting = len(segments) - 1 + PrebuiltToolSupport.nesting_level(value)
        if nesting > PREBUILT_MAX_JSON_NESTING:
            problem = f"the value would sit under {len(segments) - 1} containers and nest the document {nesting} levels deep"
            raise PrebuiltToolSupport.argument_error("pointer", problem, f"a pointer and value nested at most {PREBUILT_MAX_JSON_NESTING} levels together")

        # Find the parent, creating missing objects when asked, and put
        # the value in its place.
        parent, key = JsonDataToolFunctions._parent_slot(holder, segments, create_missing, "pointer", "the pointer")
        replaced = JsonDataToolFunctions._slot_insert(parent, key, value, False, False, "pointer", "the pointer")
        return {"json": json.dumps(holder[""], separators=_COMPACT_SEPARATORS, ensure_ascii=False), "replaced": replaced}

    @staticmethod
    def list_json_paths(
        json_text: Annotated[str, Field(description=_JSON_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        leaves_only: Annotated[bool, Field(description="Whether to list only leaves, meaning scalars and empty arrays and objects. When false, every array and object is listed too, before its contents. The root is listed as the empty pointer whenever it is included. The default is true.")] = True,
    ) -> PrebuiltToolOutput:
        """List the JSON Pointer path and JSON type of every value in a document, in depth-first order with object keys in document order. Use it to explore the structure of an unfamiliar document or to find the exact path of a field before reading or changing it. By default only leaves are listed, meaning scalars and empty containers, while leaves_only false also lists every container and the root as the empty pointer. At most 1,000 paths are listed while count covers every path, and invalid JSON fails naming json_text."""
        document = PrebuiltToolSupport.parse_json_text(json_text, "json_text")

        # Write paths one at a time so the item cap and the character
        # budget can stop the list, then count the rest without writing
        # their pointers.
        steps = JsonDataToolFunctions._path_steps(document, leaves_only)
        paths, truncated = PrebuiltToolSupport.cap_items(map(JsonDataToolFunctions._path_entry, steps))
        count = len(paths) + int(truncated) + sum(1 for _ in steps)
        return {"paths": paths, "count": count, "truncated": truncated}

    @staticmethod
    def diff_json_documents(
        original_json: Annotated[str, Field(description="The earlier version of the document, given as the text of one JSON document. Changes are reported as the edits that turn this document into the modified one. It is parsed with the usual JSON rules, so NaN and Infinity are refused. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
        modified_json: Annotated[str, Field(description="The later version of the document, given as the text of one JSON document. Added object keys are reported in this document's key order. It is parsed with the usual JSON rules, so NaN and Infinity are refused. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """List the additions, removals, and replacements that turn one JSON document into another, each with its pointer and its old and new values. Use it to see exactly what changed between two versions of a configuration, an API response, or any other JSON. Objects are compared key by key and arrays index by index, and equality is type-aware, so a boolean never equals a number, while an integer equals a float of the same value. At most 1,000 changes are listed while count covers every change, and invalid JSON fails naming the parameter that holds it."""
        original = PrebuiltToolSupport.parse_json_text(original_json, "original_json")
        modified = PrebuiltToolSupport.parse_json_text(modified_json, "modified_json")

        # Write changes one at a time so the item cap and the character
        # budget can stop the list, then count the rest without writing
        # their pointers.
        steps = JsonDataToolFunctions._change_steps(original, modified)
        changes, truncated = PrebuiltToolSupport.cap_items(map(JsonDataToolFunctions._change_entry, steps))
        count = len(changes) + int(truncated) + sum(1 for _ in steps)
        return {"identical": count == 0, "changes": changes, "count": count, "truncated": truncated}

    @staticmethod
    def apply_json_patch(
        json_text: Annotated[str, Field(description=_JSON_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)],
        patch_json: Annotated[str, Field(description="The JSON Patch to apply, given as the text of a JSON array of operation objects. Each operation has an op member and a path member, plus from for move and copy and value for add, replace, and test. At most 1,000 operations are allowed, and they run in order. The text may hold at most one million characters.", max_length=PREBUILT_MAX_TEXT_CHARS)],
    ) -> PrebuiltToolOutput:
        """Apply an RFC 6902 JSON Patch to a document, all or nothing, and return the patched document as compact JSON. Use it to make several precise edits in one step, or to apply a patch that another system produced. The supported operations are add, remove, replace, move, copy, and test, and at most 1,000 operations are allowed. Any failing operation, a failed test included, fails naming patch_json with the operation index and reason, and so does a result that would grow past one million characters or 100 levels of nesting."""
        # Read the document into a one-member holder so even the root
        # has a parent, and start the running size at its length.
        holder: dict[str, object] = {"": PrebuiltToolSupport.parse_json_text(json_text, "json_text")}
        operations = JsonDataToolFunctions._patch_operations(patch_json)
        size = len(json.dumps(holder[""], separators=_COMPACT_SEPARATORS, ensure_ascii=False))
        for index, operation in enumerate(operations):
            # Check the operation's members and split its paths.
            kind, target, source, value = JsonDataToolFunctions._operation_fields(operation, index)
            context = f"operation {index} ({kind})"

            # Read the value the operation takes, copies, or checks,
            # taking it out of the document for remove and move.
            current: object = _ABSENT
            if source is not None:
                source_parent, source_key = JsonDataToolFunctions._parent_slot(holder, source, False, "patch_json", context)
                current = JsonDataToolFunctions._slot_value(source_parent, source_key, kind in _TAKING_OPERATIONS, context)

            # A test only compares the value it read.
            if kind == "test":
                if not JsonDataToolFunctions._same_json(current, value):
                    raise PrebuiltToolSupport.argument_error("patch_json", f"{context} found a different value at its path", _PATCH_EXPECTED)
                continue

            # Work out the value to insert while keeping the running
            # size and the nesting under their caps, then insert it.
            inserted, size = JsonDataToolFunctions._measured_insertion(kind, current, value, size, len(target) - 1, index)
            if inserted is not _ABSENT:
                parent, key = JsonDataToolFunctions._parent_slot(holder, target, False, "patch_json", context)
                JsonDataToolFunctions._slot_insert(parent, key, inserted, kind != "replace", kind == "replace", "patch_json", context)

        # Every operation succeeded, so write the patched document.
        return {"json": json.dumps(holder[""], separators=_COMPACT_SEPARATORS, ensure_ascii=False), "applied_operations": len(operations)}

    @staticmethod
    def summarize_json_structure(json_text: Annotated[str, Field(description=_JSON_TEXT_PARAMETER_DESCRIPTION, max_length=PREBUILT_MAX_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Describe the shape of a JSON document: its top-level type, how deeply it nests, how many values it holds, and a merged outline of its keys and types. Use it to understand an unfamiliar or very large document before reading parts of it. In the outline a scalar becomes its type name, an object maps each key to the outline of its value, and an array becomes one merged outline of its items, where a key that some items lack ends in a question mark and mixed types are joined with a vertical bar. Invalid JSON or nesting deeper than 100 levels fails naming json_text."""
        document = PrebuiltToolSupport.parse_json_text(json_text, "json_text")
        return {
            "top_level_type": _JSON_TYPES[type(document)].value,
            "max_nesting": PrebuiltToolSupport.nesting_level(document),
            "value_count": JsonDataToolFunctions._value_count(document),
            "shape": JsonDataToolFunctions._merged_shape(document),
        }

    @staticmethod
    def extract_json_from_text(text: Annotated[str, Field(description="The text to search for embedded JSON, given as plain characters. Positions in the result count Unicode code points from 0, and each end position is just past its document. Only objects and arrays are extracted, never bare numbers or strings. The text may hold at most one hundred thousand characters.", max_length=PREBUILT_MAX_MEDIUM_TEXT_CHARS)]) -> PrebuiltToolOutput:
        """Find the JSON objects and arrays embedded in surrounding text, such as a model reply or a log line, and return each parsed value with its start and end positions. Use it to recover structured data from text that mixes prose and JSON. Candidates are tried at each opening brace or bracket from left to right, scalars are never extracted, documents never overlap, and a candidate that is invalid, holds NaN or Infinity, or nests deeper than 100 levels is skipped. At most 1,000 start positions are tried before truncated is set, and the tool has no failure case beyond the text length cap."""
        # Decode at each opening bracket, left to right, noting any
        # non-finite constant instead of accepting it; the shared float
        # hook refuses a number too large for a float.
        constants: list[str] = []
        read_float = partial(PrebuiltToolSupport._read_json_float, "text")
        decoder = json.JSONDecoder(parse_float=read_float, parse_constant=constants.append)
        found: list[dict[str, object]] = []
        position, starts, scan_truncated = 0, 0, False
        while (match := _OPENING_BRACKET.search(text, position)) is not None:
            if starts == PREBUILT_MAX_JSON_SCAN_STARTS:
                scan_truncated = True
                break
            starts += 1
            constants.clear()
            try:
                value, end = decoder.raw_decode(text, match.start())
            except (ValueError, RecursionError, ToolExecutionError):
                position = match.start() + 1
                continue

            # @intent prebuilt-json-nesting-cap
            # A candidate nested past the cap, or one holding a
            # non-finite constant, is skipped like any invalid one, and
            # the scan goes on at the next start position.
            if constants or PrebuiltToolSupport.nesting_level(value) > PREBUILT_MAX_JSON_NESTING:
                position = match.start() + 1
                continue

            # Keep the document and continue after it, so documents
            # never overlap.
            found.append({"start": match.start(), "end": end, "value": value})
            position = end
        documents, budget_truncated = PrebuiltToolSupport.cap_items(found)
        return {"documents": documents, "count": len(found), "truncated": scan_truncated or budget_truncated}

    @staticmethod
    def _formatted_length(document: object, indent: int, ensure_ascii: bool) -> int:
        """Predict the length of json.dumps output: the compact length plus the spaces and line breaks indentation adds."""
        # The compact text is measured piece by piece and never held.
        encoder = json.JSONEncoder(separators=_COMPACT_SEPARATORS, ensure_ascii=ensure_ascii)
        total = sum(map(len, encoder.iterencode(document)))
        if indent == 0:
            return total
        # Indenting adds a space after each colon, and a line break and
        # indent before every item of a non-empty container and before
        # its closing bracket.
        pending: list[tuple[object, int]] = [(document, 0)] if isinstance(document, (dict, list)) else []
        while pending:
            value, level = pending.pop()
            items: Collection[object] = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
            total += len(value) if isinstance(value, dict) else 0
            if items:
                total += len(items) * (1 + indent * (level + 1)) + 1 + indent * level
            pending.extend((child, level + 1) for child in items if isinstance(child, (dict, list)))
        return total

    @staticmethod
    def _lookup(document: object, segments: list[str]) -> tuple[bool, object]:
        """Follow pointer segments from the document, returning whether a value exists there and the value."""
        current = document
        for segment in segments:
            if isinstance(current, dict) and segment in current:
                current = current[segment]
            elif isinstance(current, list) and _ARRAY_INDEX.fullmatch(segment) and int(segment) < len(current):
                current = current[int(segment)]
            else:
                return False, None
        return True, current

    @staticmethod
    def _parent_slot(holder: dict[str, object], segments: list[str], create_missing: bool, parameter: str, context: str) -> tuple[dict[str, object] | list[object], str]:
        """Walk to the container that holds the last segment, creating missing objects when asked; return it with that segment."""
        expected = "a pointer whose parent objects and arrays already exist"
        parent: dict[str, object] | list[object] = holder
        for position, segment in enumerate(segments[:-1]):
            child: object = _ABSENT
            if isinstance(parent, dict):
                child = parent.get(segment, _ABSENT)
                if child is _ABSENT and create_missing:
                    child = parent[segment] = {}
            elif _ARRAY_INDEX.fullmatch(segment) and int(segment) < len(parent):
                child = parent[int(segment)]
            if child is _ABSENT:
                raise PrebuiltToolSupport.argument_error(parameter, f"{context} names a parent at segment {position} that does not exist", expected)
            if not isinstance(child, (dict, list)):
                raise PrebuiltToolSupport.argument_error(parameter, f"{context} passes through a value at segment {position} that is not an object or array", expected)
            parent = child
        return parent, segments[-1]

    @staticmethod
    def _slot_value(parent: dict[str, object] | list[object], key: str, take: bool, context: str) -> object:
        """Return the member or item a key names, removing it when take is true; a missing one is a patch error."""
        if isinstance(parent, dict) and key in parent:
            return parent.pop(key) if take else parent[key]
        if isinstance(parent, list) and _ARRAY_INDEX.fullmatch(key) and int(key) < len(parent):
            return parent.pop(int(key)) if take else parent[int(key)]
        raise PrebuiltToolSupport.argument_error("patch_json", f"{context} names a value that does not exist", _PATCH_EXPECTED)

    @staticmethod
    def _slot_insert(parent: dict[str, object] | list[object], key: str, value: object, shift_items: bool, must_exist: bool, parameter: str, context: str) -> bool:
        """Put a value at a member or array position and say whether it replaced one; shift_items inserts before an existing item."""
        expected = "a pointer to an existing member or item, or to the end of an array"
        if isinstance(parent, dict):
            replaced = key in parent
            if must_exist and not replaced:
                raise PrebuiltToolSupport.argument_error(parameter, f"{context} names a member that does not exist", expected)
            parent[key] = value
            return replaced
        size = len(parent)
        position = size if key == "-" else int(key) if _ARRAY_INDEX.fullmatch(key) else size + 1
        if position > size or (must_exist and position == size):
            raise PrebuiltToolSupport.argument_error(parameter, f"{context} names no existing index or end position of an array of {size} items", expected)
        if position < size and not shift_items:
            parent[position] = value
            return True
        parent.insert(position, value)
        return False

    @staticmethod
    def _patch_operations(patch_json: str) -> list[dict[str, object]]:
        """Parse the patch text into its list of operation objects, refusing anything else."""
        operations = PrebuiltToolSupport.parse_json_text(patch_json, "patch_json")
        expected = f"a JSON array of at most {PREBUILT_MAX_PATCH_OPERATIONS} operation objects"
        if not isinstance(operations, list):
            raise PrebuiltToolSupport.argument_error("patch_json", "the patch is not a JSON array", expected)
        if len(operations) > PREBUILT_MAX_PATCH_OPERATIONS:
            raise PrebuiltToolSupport.argument_error("patch_json", f"the patch holds {len(operations)} operations", expected)
        checked: list[dict[str, object]] = []
        for index, operation in enumerate(operations):
            if not isinstance(operation, dict):
                raise PrebuiltToolSupport.argument_error("patch_json", f"operation {index} is not an object", expected)
            checked.append(operation)
        return checked

    @staticmethod
    def _operation_fields(operation: dict[str, object], index: int) -> tuple[str, list[str], list[str] | None, object]:
        """Check one operation's members and return its op, target segments, source segments, and value."""
        # The op must be one of the six, and each pointer it needs must
        # be well formed; segments start with the holder's empty key.
        kind = operation.get("op")
        if not isinstance(kind, str) or kind not in _PATCH_POINTERS:
            raise PrebuiltToolSupport.argument_error("patch_json", f"operation {index} has no op member naming a JSON Patch operation", _PATCH_EXPECTED)
        paths: dict[str, list[str]] = {}
        for member in _PATCH_POINTERS[kind]:
            pointer = operation.get(member)
            if not isinstance(pointer, str) or _BAD_POINTER.search(pointer):
                raise PrebuiltToolSupport.argument_error("patch_json", f"operation {index} ({kind}) needs a {member} member that is a valid JSON Pointer", _PATCH_EXPECTED)
            paths[member] = ["", *PrebuiltToolSupport.json_pointer_tokens(pointer, "patch_json")]
        if kind in _VALUE_OPERATIONS and "value" not in operation:
            raise PrebuiltToolSupport.argument_error("patch_json", f"operation {index} ({kind}) has no value member", _PATCH_EXPECTED)

        # The whole document cannot be removed, and a value cannot move
        # into its own contents.
        target = paths["path"]
        if kind == "remove" and len(target) == 1:
            raise PrebuiltToolSupport.argument_error("patch_json", f"operation {index} (remove) would remove the whole document", _PATCH_EXPECTED)
        origin = paths.get("from", target)
        if kind == "move" and len(origin) < len(target) and target[: len(origin)] == origin:
            raise PrebuiltToolSupport.argument_error("patch_json", f"operation {index} (move) would move a value into itself", _PATCH_EXPECTED)
        value = operation.get("value", _ABSENT) if kind in _VALUE_OPERATIONS else _ABSENT
        return kind, target, None if kind == "add" else origin, value

    @staticmethod
    def _measured_insertion(kind: str, current: object, value: object, size: int, path_length: int, index: int) -> tuple[object, int]:
        """Return the value an operation inserts and the new running size, refusing growth past the size or nesting cap."""
        inserted = current if kind in {"move", "copy"} else value
        added = len(json.dumps(inserted, separators=_COMPACT_SEPARATORS, ensure_ascii=False)) if kind in _INSERTING_OPERATIONS else 0
        removed = len(json.dumps(current, separators=_COMPACT_SEPARATORS, ensure_ascii=False)) if kind in _REMOVING_OPERATIONS else 0

        # @intent prebuilt-output-text-cap
        # The running size grows by each inserted value and shrinks by
        # each removed one, so a chain of copies is refused as soon as
        # it passes the cap instead of doubling the document each time.
        if size + added - removed > PREBUILT_MAX_TEXT_CHARS:
            problem = f"operation {index} ({kind}) would make the document longer than {PREBUILT_MAX_TEXT_CHARS} characters"
            raise PrebuiltToolSupport.argument_error("patch_json", problem, "a patch whose result fits the cap")

        # @intent prebuilt-json-nesting-cap
        # Each path segment adds one container above the inserted value,
        # and the document must stay within the nesting cap so copies
        # and the final json.dumps never recurse too deep.
        if inserted is not _ABSENT and path_length + PrebuiltToolSupport.nesting_level(inserted) > PREBUILT_MAX_JSON_NESTING:
            problem = f"operation {index} ({kind}) would nest the document deeper than {PREBUILT_MAX_JSON_NESTING} levels"
            raise PrebuiltToolSupport.argument_error("patch_json", problem, "a patch whose result stays within the nesting cap")
        return (copy.deepcopy(inserted) if kind == "copy" else inserted), size + added - removed

    @staticmethod
    def _same_json(first: object, second: object) -> bool:
        """Compare two JSON values type-aware: true is not 1, while 1 equals 1.0, and objects ignore key order."""
        pending: list[tuple[object, object]] = [(first, second)]
        while pending:
            left, right = pending.pop()
            if _JSON_TYPES.get(type(left)) is not _JSON_TYPES.get(type(right)):
                return False
            if isinstance(left, dict) and isinstance(right, dict):
                if left.keys() != right.keys():
                    return False
                pending.extend((left[key], right[key]) for key in left)
            elif isinstance(left, list) and isinstance(right, list):
                if len(left) != len(right):
                    return False
                pending.extend(zip(left, right, strict=True))
            elif left != right:
                return False
        return True

    @staticmethod
    def _path_steps(document: object, leaves_only: bool) -> Iterator[tuple[str, str | None, object]]:
        """Yield (parent pointer, segment, value) for each listed value in depth-first pre-order; the root has no segment."""
        root_has_items = isinstance(document, (dict, list)) and len(document) > 0
        if not leaves_only or not root_has_items:
            yield "", None, document
        # Each frame holds a container's pointer and an iterator over
        # its members or items, so only one pointer per level is held.
        frames: list[tuple[str, Iterator[tuple[str | int, object]]]] = []
        if isinstance(document, (dict, list)) and root_has_items:
            frames.append(("", iter(document.items()) if isinstance(document, dict) else enumerate(document)))
        while frames:
            prefix, children = frames[-1]
            step = next(children, None)
            if step is None:
                frames.pop()
                continue
            segment, value = str(step[0]), step[1]
            has_items = isinstance(value, (dict, list)) and len(value) > 0
            if not leaves_only or not has_items:
                yield prefix, segment, value
            if isinstance(value, (dict, list)) and has_items:
                pointer = prefix + "/" + segment.replace("~", "~0").replace("/", "~1")
                frames.append((pointer, iter(value.items()) if isinstance(value, dict) else enumerate(value)))

    @staticmethod
    def _path_entry(step: tuple[str, str | None, object]) -> dict[str, str]:
        """Write one listed value as its pointer and JSON type."""
        prefix, segment, value = step
        pointer = prefix if segment is None else prefix + "/" + segment.replace("~", "~0").replace("/", "~1")
        return {"pointer": pointer, "type": _JSON_TYPES[type(value)].value}

    @staticmethod
    def _change_steps(original: object, modified: object) -> Iterator[tuple[str, str | None, JsonChangeKind, object, object]]:
        """Yield (parent pointer, segment, change, old value, new value) for every difference, in the row's order."""
        pending: list[tuple[str, str | None, object, object]] = [("", None, original, modified)]
        while pending:
            prefix, segment, old, new = pending.pop()
            if old is _ABSENT or new is _ABSENT:
                yield prefix, segment, JsonChangeKind.ADD if old is _ABSENT else JsonChangeKind.REMOVE, None if old is _ABSENT else old, None if new is _ABSENT else new
                continue
            pointer = prefix if segment is None else prefix + "/" + segment.replace("~", "~0").replace("/", "~1")
            # Matching objects compare removed and shared keys in the
            # original order, then add new keys in the modified order.
            if isinstance(old, dict) and isinstance(new, dict):
                steps = [(pointer, key, value, new.get(key, _ABSENT)) for key, value in old.items()]
                steps += [(pointer, key, _ABSENT, value) for key, value in new.items() if key not in old]
            # Matching arrays compare shared indexes, add extra items in
            # ascending order, and remove extra items from the end down.
            elif isinstance(old, list) and isinstance(new, list):
                shared = min(len(old), len(new))
                steps = [(pointer, str(position), old[position], new[position]) for position in range(shared)]
                steps += [(pointer, str(position), _ABSENT, new[position]) for position in range(shared, len(new))]
                steps += [(pointer, str(position), old[position], _ABSENT) for position in reversed(range(shared, len(old)))]
            # Anything else is one replacement unless the values are the
            # same type and equal.
            else:
                if _JSON_TYPES[type(old)] is not _JSON_TYPES[type(new)] or old != new:
                    yield prefix, segment, JsonChangeKind.REPLACE, old, new
                continue
            pending.extend(reversed(steps))

    @staticmethod
    def _change_entry(step: tuple[str, str | None, JsonChangeKind, object, object]) -> dict[str, object]:
        """Write one difference as its operation, pointer, and old and new values."""
        prefix, segment, change, old, new = step
        pointer = prefix if segment is None else prefix + "/" + segment.replace("~", "~0").replace("/", "~1")
        return {"op": change.value, "pointer": pointer, "old_value": old, "new_value": new}

    @staticmethod
    def _value_count(document: object) -> int:
        """Count every value in a document, containers included."""
        count = 1
        pending = [document]
        while pending:
            value = pending.pop()
            children: Collection[object] = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
            count += len(children)
            pending.extend(child for child in children if isinstance(child, (dict, list)))
        return count

    @staticmethod
    def _merged_shape(document: object) -> object:
        """Build the shape outline of a document, merging the values found at the same place into one shape."""
        # Each work item is a list of values that share one place in
        # the outline and a setter that stores their merged shape.
        root: list[object] = [None]
        pending: list[tuple[list[object], Callable[[object], None]]] = [([document], partial(root.__setitem__, 0))]
        while pending:
            values, store = pending.pop()
            names = sorted({_JSON_TYPES[type(value)].value for value in values})
            # Objects merge key by key, and a key that some of them lack
            # gets a question mark.
            if names == [JsonType.OBJECT.value]:
                members: dict[str, list[object]] = {}
                for key, child in [pair for value in values if isinstance(value, dict) for pair in value.items()]:
                    members.setdefault(key, []).append(child)
                shape: dict[str, object] = {}
                for key, children in members.items():
                    label = key if len(children) == len(values) else key + "?"
                    shape[label] = None
                    pending.append((children, partial(shape.__setitem__, label)))
                store(shape)
            # Arrays merge all their items into one item shape.
            elif names == [JsonType.ARRAY.value]:
                items = [item for value in values if isinstance(value, list) for item in value]
                inner: list[object] = [None] if items else []
                if items:
                    pending.append((items, partial(inner.__setitem__, 0)))
                store(inner)
            # Equal scalar types keep their name; any other mix lists
            # the distinct type names in sorted order.
            else:
                store("|".join(names))
        return root[0]

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.verify_json_syntax,
            cls.format_json,
            cls.json_get_value,
            cls.json_set_value,
            cls.list_json_paths,
            cls.diff_json_documents,
            cls.apply_json_patch,
            cls.summarize_json_structure,
            cls.extract_json_from_text,
        )


__all__ = ["JsonDataToolFunctions"]
