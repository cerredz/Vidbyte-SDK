"""FILE: vidbyte/lib/dataclasses/validation.py

PURPOSE: Defines RecordFieldValidator, the one canonical field validator for validated records (text, optional text, positive finite numbers, bounded ints, strict bools, enum members, argv tuples and absolute directories), and RecordFieldConverter, the canonical conversions and checks records apply beside it (tuples, read-only mappings, enum members, paths and plain instance checks).
ROLE IN CODEBASE: Called from the __post_init__ of the records in vidbyte/lib/dataclasses/native_threads.py and process.py, and by the output readers GrokWire, OpencodeWire and MuseWire under vidbyte/harnesses/native/.
ARCHITECTURE NOTE: Two classes of static methods, each taking the checked value first and the field name second, returning the checked or converted value or raising ConfigurationError. The checked variable is always named value, so the bool guards here are the single owner lint rules C002, C006, C007 and C008 point at. Messages name the field and the expected type or range, and quote a value only when it is a short, non-secret scalar or text. Every ConfigurationError also carries details["field"], so a caller can name the bad argument without reading the message text.
FUNCTION INVENTORY: require_text, require_optional_text, require_number, require_int, require_bool, require_enum, require_argv, require_directory; _text_problem words what a text value fails, and _received renders the received value safely for a message. RecordFieldConverter: to_tuple, to_mapping, to_enum (a member or its exact value string), to_path (a str or os.PathLike, unchecked), require_instance.
COMMON MODIFICATION PATTERNS: Add a new check as one more static method with value first and field_name second, and call it from a record's __post_init__; never copy a check into a record.
WHAT NOT TO DO IN THIS FILE: 1. Do not convert values silently; to_path only wraps a path in Path and never checks or resolves it. 2. Do not quote mapping values or long text in a message; they can hold secrets. 3. Do not import from a layer above vidbyte.lib.
KNOWN EDGE CASES: bool is an int subclass, so every numeric check refuses bool first. A field whose last name segment reads as a credential (password, token, secret, api_key) is never quoted, whatever its length. require_argv refuses a list on purpose, because argv fields must be immutable tuples. require_directory must run on the path as given, before Path.resolve(), or a relative path would pass.
RELATED DOCS: vidbyte/lib/README.md; lint/rules/c008_shared_validator_owner.py
TESTS: tests/features/harness_threads/test_harness_threads_records.py
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from vidbyte.lib.constants.native_threads import NATIVE_QUOTED_VALUE_MAX_CHARS
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.util.credential_keys import CredentialKeyPolicy

EnumT = TypeVar("EnumT", bound=Enum)


class RecordFieldValidator:
    """The canonical field checks every validated record uses."""

    @staticmethod
    def require_text(value: Any, field_name: str, *, max_chars: int, pattern: str | None = None, allow_blank: bool = False) -> str:
        # A str of at most max_chars, fully matching pattern when one
        # is given; it may be empty or blank only with allow_blank.
        problem = RecordFieldValidator._text_problem(value, max_chars=max_chars, pattern=pattern, allow_blank=allow_blank)
        if problem is not None:
            raise ConfigurationError(f"{field_name} must {problem}; got {RecordFieldValidator._received(value, field_name)}.", details={"field": field_name})
        return value

    @staticmethod
    def require_optional_text(value: Any, field_name: str, *, max_chars: int, pattern: str | None = None) -> str | None:
        # None, or what require_text accepts.
        problem = None if value is None else RecordFieldValidator._text_problem(value, max_chars=max_chars, pattern=pattern, allow_blank=False)
        if problem is not None:
            raise ConfigurationError(f"{field_name} must {problem}; got {RecordFieldValidator._received(value, field_name)}.", details={"field": field_name})
        return value

    @staticmethod
    def require_number(value: Any, field_name: str, *, maximum: float) -> float:
        # An int or float, not bool, finite, greater than 0
        # and at most maximum.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0 or value > maximum:
            raise ConfigurationError(f"{field_name} must be a finite number greater than 0 and at most {maximum}; got {RecordFieldValidator._received(value, field_name)}.", details={"field": field_name})
        return value

    @staticmethod
    def require_int(value: Any, field_name: str, *, minimum: int, maximum: int) -> int:
        # An int, not bool, in [minimum, maximum].
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
            raise ConfigurationError(f"{field_name} must be an integer from {minimum} to {maximum}; got {RecordFieldValidator._received(value, field_name)}.", details={"field": field_name})
        return value

    @staticmethod
    def require_bool(value: Any, field_name: str) -> bool:
        # Exactly True or False.
        if not isinstance(value, bool):
            raise ConfigurationError(f"{field_name} must be True or False; got {RecordFieldValidator._received(value, field_name)}.", details={"field": field_name})
        return value

    @staticmethod
    def require_enum(value: Any, enum_type: type[EnumT], field_name: str) -> EnumT:
        # A member of enum_type, never its value string.
        if not isinstance(value, enum_type):
            raise ConfigurationError(f"{field_name} must be a {enum_type.__name__} member; got {RecordFieldValidator._received(value, field_name)}.", details={"field": field_name})
        return value

    @staticmethod
    def require_argv(value: Any, field_name: str) -> tuple[str, ...]:
        # A non-empty tuple of non-empty str items without NUL.
        if not isinstance(value, tuple) or not value or not all(isinstance(item, str) and item and "\x00" not in item for item in value):
            raise ConfigurationError(f"{field_name} must be a non-empty tuple of non-empty strings without NUL characters; got {RecordFieldValidator._received(value, field_name)}.", details={"field": field_name})
        return value

    @staticmethod
    def require_directory(value: Any, field_name: str) -> Path:
        # A Path that is absolute and an existing directory.
        if not isinstance(value, Path) or not value.is_absolute() or not value.is_dir():
            raise ConfigurationError(f"{field_name} must be an absolute path to an existing directory; got a value of type {type(value).__name__} that is not one.", details={"field": field_name})
        return value

    @staticmethod
    def _text_problem(value: Any, *, max_chars: int, pattern: str | None, allow_blank: bool) -> str | None:
        # What a text value fails, worded to follow "must", or None.
        if not isinstance(value, str) or (not allow_blank and not value.strip()) or len(value) > max_chars:
            return f"be {'text' if allow_blank else 'non-empty text'} of at most {max_chars} characters"
        if pattern is not None and re.fullmatch(pattern, value) is None:
            return f"match {pattern}"
        return None

    @staticmethod
    def _received(value: Any, field_name: str) -> str:
        # @intent validator-messages-never-quote-secrets
        # Quotes a short non-secret scalar or text; otherwise names only
        # the type, so secrets and long text never reach a message.
        secret = CredentialKeyPolicy.is_secret_key(field_name.rsplit(".", 1)[-1])
        quotable = value is None or isinstance(value, (bool, int, float, Enum, str))
        if secret or not quotable or len(repr(value)) > NATIVE_QUOTED_VALUE_MAX_CHARS:
            return f"a value of type {type(value).__name__}"
        return repr(value)


class RecordFieldConverter:
    """The canonical conversions records apply: tuple fields to tuples, mapping fields to read-only copies, enum values to members, paths to Path, and plain instance checks."""

    @staticmethod
    def to_tuple(value: Any, field_name: str, *, item_type: type[Any] | tuple[type[Any], ...], max_items: int | None = None) -> tuple[Any, ...]:
        # A tuple or list whose items are all item_type
        # instances, stored as a tuple; a str is refused because
        # it is not a list of items.
        if not isinstance(value, (tuple, list)) or not all(isinstance(item, item_type) and not isinstance(item, bool) for item in value):
            raise ConfigurationError(f"{field_name} must be a tuple of {RecordFieldConverter._type_names(item_type)} items; got a value of type {type(value).__name__}.", details={"field": field_name})
        if max_items is not None and len(value) > max_items:
            raise ConfigurationError(f"{field_name} may hold at most {max_items} items; got {len(value)}.", details={"field": field_name})
        return tuple(value)

    @staticmethod
    def to_mapping(value: Any, field_name: str) -> MappingProxyType[str, str]:
        # A read-only copy of a mapping of text to text;
        # values are never quoted.
        if not isinstance(value, Mapping) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
            raise ConfigurationError(f"{field_name} must be a mapping of text keys to text values; got a value of type {type(value).__name__}.", details={"field": field_name})
        return MappingProxyType(dict(value))

    @staticmethod
    def to_enum(value: Any, enum_type: type[EnumT], field_name: str) -> EnumT:
        # A member of enum_type, or the exact value string of one,
        # returned as the member; case is not folded.
        if isinstance(value, enum_type):
            return value
        members = {str(member.value): member for member in enum_type}
        if isinstance(value, str) and value in members:
            return members[value]
        raise ConfigurationError(f"{field_name} must be one of {', '.join(members)}; got {RecordFieldValidator._received(value, field_name)}.", details={"field": field_name})

    @staticmethod
    def to_path(value: Any, field_name: str) -> Path:
        # A str or os.PathLike naming a text path, wrapped in Path as
        # given; it is neither checked nor resolved here.
        text = os.fspath(value) if isinstance(value, (str, os.PathLike)) else None
        if not isinstance(text, str):
            raise ConfigurationError(f"{field_name} must be a str or os.PathLike path; got a value of type {type(value).__name__}.", details={"field": field_name})
        return Path(text)

    @staticmethod
    def require_instance(value: Any, field_name: str, expected: type[Any] | tuple[type[Any], ...], *, optional: bool = False) -> Any:
        # An instance of expected (never a bool standing in for an int),
        # or None when optional.
        if value is None and optional:
            return None
        if not isinstance(value, expected) or (isinstance(value, bool) and bool not in RecordFieldConverter._types(expected)):
            raise ConfigurationError(f"{field_name} must be {RecordFieldConverter._type_names(expected)}{' or None' if optional else ''}; got a value of type {type(value).__name__}.", details={"field": field_name})
        return value

    @staticmethod
    def _types(expected: type[Any] | tuple[type[Any], ...]) -> tuple[type[Any], ...]:
        # Normalises one type or a tuple of types to a tuple.
        return expected if isinstance(expected, tuple) else (expected,)

    @staticmethod
    def _type_names(expected: type[Any] | tuple[type[Any], ...]) -> str:
        # Renders the expected type names for a message.
        return " or ".join(item.__name__ for item in (expected if isinstance(expected, tuple) else (expected,)))


__all__ = ["RecordFieldConverter", "RecordFieldValidator"]
