"""FILE: vidbyte/lib/dataclasses/validation.py

PURPOSE: Defines RecordFieldValidator, the one canonical field validator for validated records: text, optional text, positive finite numbers, bounded ints, optional counts, strict bools, enum members, enum sets, argv tuples, text mappings, UUIDs, absolute directories and non-negative decimals.
ROLE IN CODEBASE: Called from the __post_init__ of the records in vidbyte/lib/dataclasses/native_hosts.py, grok.py, opencode.py, muse.py, harness_backends.py and process.py, by McpStdioTransport in vidbyte/tools/mcp/transport.py for its new options, and by the native tool argument parser in vidbyte/tools/builtins/native_host_tool.py.
ARCHITECTURE NOTE: A class of static methods, each taking the checked value first and the field name second, returning the checked (and for sets, converted) value or raising ConfigurationError. The checked variable is always named value, so the bool guards here are the single owner lint rules C002, C006, C007 and C008 point at. Messages name the field and the expected type or range, and quote a value only when it is a short, non-secret scalar or text.
FUNCTION INVENTORY: require_text, require_optional_text, require_number, require_int, require_optional_count, require_bool, require_enum, require_enum_set, require_argv, require_text_mapping, require_uuid, require_directory, require_decimal; _received renders the received value safely for a message.
COMMON MODIFICATION PATTERNS: Add a new check as one more static method with value first and field_name second, and call it from a record's __post_init__; never copy a check into a record.
WHAT NOT TO DO IN THIS FILE: 1. Do not convert values silently, except a set to a frozenset in require_enum_set. 2. Do not quote mapping values or long text in a message; they can hold secrets. 3. Do not import from a layer above vidbyte.lib.
KNOWN EDGE CASES: bool is an int subclass, so every numeric check refuses bool first. A field whose last name segment reads as a credential (password, token, secret) is never quoted, whatever its length. require_argv refuses a list on purpose, because argv fields must be immutable tuples.
RELATED DOCS: docs/spec/native-grok-opencode-meta-hosts/spec.md §9.1 (RecordFieldValidator); lint/rules/c008_shared_validator_owner.py
TESTS: tests/features/grok_host/test_grok_host_records.py
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.util.credential_keys import CredentialKeyPolicy

EnumT = TypeVar("EnumT", bound=Enum)

_QUOTE_MAX_CHARS = 80
_UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


class RecordFieldValidator:
    """The canonical field checks every validated record uses."""

    @staticmethod
    def require_text(value: Any, field_name: str, *, max_chars: int, pattern: str | None = None) -> str:
        # A non-blank str of at most max_chars, fully matching pattern when one is given.
        if not isinstance(value, str) or not value.strip() or len(value) > max_chars:
            raise ConfigurationError(f"{field_name} must be non-empty text of at most {max_chars} characters; got {RecordFieldValidator._received(value, field_name)}.")
        if pattern is not None and re.fullmatch(pattern, value) is None:
            raise ConfigurationError(f"{field_name} must match {pattern}; got {RecordFieldValidator._received(value, field_name)}.")
        return value

    @staticmethod
    def require_optional_text(value: Any, field_name: str, *, max_chars: int, pattern: str | None = None) -> str | None:
        # None, or what require_text accepts.
        if value is None:
            return None
        return RecordFieldValidator.require_text(value, field_name, max_chars=max_chars, pattern=pattern)

    @staticmethod
    def require_number(value: Any, field_name: str, *, maximum: float) -> float:
        # An int or float, not bool, finite, greater than 0 and at most maximum.
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0 or value > maximum:
            raise ConfigurationError(f"{field_name} must be a finite number greater than 0 and at most {maximum}; got {RecordFieldValidator._received(value, field_name)}.")
        return value

    @staticmethod
    def require_int(value: Any, field_name: str, *, minimum: int, maximum: int) -> int:
        # An int, not bool, in [minimum, maximum].
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
            raise ConfigurationError(f"{field_name} must be an integer from {minimum} to {maximum}; got {RecordFieldValidator._received(value, field_name)}.")
        return value

    @staticmethod
    def require_optional_count(value: Any, field_name: str) -> int | None:
        # None, or an int of at least 0 that is not bool.
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfigurationError(f"{field_name} must be None or an integer of at least 0; got {RecordFieldValidator._received(value, field_name)}.")
        return value

    @staticmethod
    def require_bool(value: Any, field_name: str) -> bool:
        # Exactly True or False.
        if not isinstance(value, bool):
            raise ConfigurationError(f"{field_name} must be True or False; got {RecordFieldValidator._received(value, field_name)}.")
        return value

    @staticmethod
    def require_enum(value: Any, enum_type: type[EnumT], field_name: str) -> EnumT:
        # A member of enum_type, never its value string.
        if not isinstance(value, enum_type):
            raise ConfigurationError(f"{field_name} must be a {enum_type.__name__} member; got {RecordFieldValidator._received(value, field_name)}.")
        return value

    @staticmethod
    def require_enum_set(value: Any, enum_type: type[EnumT], field_name: str) -> frozenset[EnumT]:
        # A set or frozenset whose items are all enum_type members, stored as a frozenset.
        if not isinstance(value, (set, frozenset)) or not all(isinstance(item, enum_type) for item in value):
            raise ConfigurationError(f"{field_name} must be a set or frozenset of {enum_type.__name__} members; got {RecordFieldValidator._received(value, field_name)}.")
        return frozenset(value)

    @staticmethod
    def require_argv(value: Any, field_name: str) -> tuple[str, ...]:
        # A non-empty tuple of non-empty str items without NUL.
        if not isinstance(value, tuple) or not value or not all(isinstance(item, str) and item and "\x00" not in item for item in value):
            raise ConfigurationError(f"{field_name} must be a non-empty tuple of non-empty strings without NUL characters; got {RecordFieldValidator._received(value, field_name)}.")
        return value

    @staticmethod
    def require_text_mapping(value: Any, field_name: str, *, key_pattern: str, max_items: int) -> Mapping[str, str]:
        # A mapping of str to str with keys fully matching key_pattern and at most max_items entries; values are never quoted.
        if not isinstance(value, Mapping) or len(value) > max_items:
            raise ConfigurationError(f"{field_name} must be a mapping of at most {max_items} text entries; got {type(value).__name__} with {len(value) if isinstance(value, Mapping) else 'no'} entries.")
        if not all(isinstance(key, str) and re.fullmatch(key_pattern, key) is not None for key in value):
            raise ConfigurationError(f"{field_name} keys must match {key_pattern}; a key does not.")
        if not all(isinstance(item, str) for item in value.values()):
            raise ConfigurationError(f"{field_name} values must all be text; a value is not.")
        return value

    @staticmethod
    def require_uuid(value: Any, field_name: str) -> str:
        # A str in the dashed 8-4-4-4-12 hexadecimal UUID form.
        if not isinstance(value, str) or _UUID_PATTERN.fullmatch(value) is None:
            raise ConfigurationError(f"{field_name} must be a UUID in the 8-4-4-4-12 hexadecimal form; got {RecordFieldValidator._received(value, field_name)}.")
        return value

    @staticmethod
    def require_directory(value: Any, field_name: str) -> Path:
        # A Path that is absolute and an existing directory.
        if not isinstance(value, Path) or not value.is_absolute() or not value.is_dir():
            raise ConfigurationError(f"{field_name} must be an absolute pathlib.Path to an existing directory; got {type(value).__name__}.")
        return value

    @staticmethod
    def require_decimal(value: Any, field_name: str) -> Decimal:
        # A finite Decimal of at least 0.
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ConfigurationError(f"{field_name} must be a finite Decimal of at least 0; got {RecordFieldValidator._received(value, field_name)}.")
        return value

    @staticmethod
    def _received(value: Any, field_name: str) -> str:
        # Quotes a short non-secret scalar or text; otherwise names only the type, so secrets and long text never reach a message.
        secret = CredentialKeyPolicy.is_secret_key(field_name.rsplit(".", 1)[-1])
        quotable = value is None or isinstance(value, (bool, int, float, Decimal, Enum, str))
        if secret or not quotable or len(repr(value)) > _QUOTE_MAX_CHARS:
            return f"a value of type {type(value).__name__}"
        return repr(value)


class RecordFieldConverter:
    """The canonical conversions records apply: tuple fields to tuples, mapping fields to read-only copies, and plain instance checks."""

    @staticmethod
    def to_tuple(value: Any, field_name: str, *, item_type: type[Any] | tuple[type[Any], ...], max_items: int | None = None) -> tuple[Any, ...]:
        # A tuple or list whose items are all item_type instances, stored as a tuple; a str is refused because it is not a list of items.
        if not isinstance(value, (tuple, list)) or not all(isinstance(item, item_type) and not isinstance(item, bool) for item in value):
            raise ConfigurationError(f"{field_name} must be a tuple of {RecordFieldConverter._type_names(item_type)} items; got a value of type {type(value).__name__}.")
        if max_items is not None and len(value) > max_items:
            raise ConfigurationError(f"{field_name} may hold at most {max_items} items; got {len(value)}.")
        return tuple(value)

    @staticmethod
    def to_mapping(value: Any, field_name: str) -> MappingProxyType[str, str]:
        # A read-only copy of a mapping of text to text; values are never quoted.
        if not isinstance(value, Mapping) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
            raise ConfigurationError(f"{field_name} must be a mapping of text keys to text values; got a value of type {type(value).__name__}.")
        return MappingProxyType(dict(value))

    @staticmethod
    def require_instance(value: Any, field_name: str, expected: type[Any] | tuple[type[Any], ...], *, optional: bool = False) -> Any:
        # An instance of expected (never a bool standing in for an int), or None when optional.
        if value is None and optional:
            return None
        if not isinstance(value, expected) or (isinstance(value, bool) and bool not in RecordFieldConverter._types(expected)):
            raise ConfigurationError(f"{field_name} must be {RecordFieldConverter._type_names(expected)}{' or None' if optional else ''}; got a value of type {type(value).__name__}.")
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
