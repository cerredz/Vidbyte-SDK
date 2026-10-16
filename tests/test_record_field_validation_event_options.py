"""FILE: tests/test_record_field_validation_event_options.py

PURPOSE: Proves the RecordFieldValidator options added for the InfiniteMemory event records and the on_event setting: require_number with allow_zero, require_utc_datetime with a resolution, and require_callable with optional and synchronous; and that a caller who passes none of the new options keeps today's behavior.
ROLE IN CODEBASE: Unit tests for vidbyte/lib/dataclasses/validation.py, row 23 of docs/spec/infinite-memory-events/spec.md section 12.3 (AC-37 b, c, d; INV-36, INV-38; D-27). tests/test_record_field_validation.py covers the older options and is not edited.
ARCHITECTURE NOTE: The validators are called directly with qualified field names such as X.f, as records do, and each refusal is checked by details['field'], which is what a record's caller reads. Each test pairs the new option with the unchanged default, so the default cannot drift while the option is added.
FUNCTION INVENTORY: test_require_number_accepts_zero_only_with_allow_zero (AC-37 d, INV-38); test_require_utc_datetime_accepts_only_a_zero_offset_at_the_resolution (AC-37 b); test_require_callable_refuses_none_unless_optional_and_async_sinks_when_synchronous (AC-37 c, INV-36, D-27). _field reads the refused field; _async_sink, _AsyncCall, and _PlainCall are the sinks.
COMMON MODIFICATION PATTERNS: A new option adds one accept case and one refuse case naming the field, next to a case proving the call without the option is unchanged.
WHAT NOT TO DO IN THIS FILE: 1. Do not split the unchanged-default cases into their own tests; alone they pass before the option exists and prove nothing about it. 2. Do not compare messages word for word beyond the field name; the spec fixes the field, not the sentence.
KNOWN EDGE CASES: inspect.iscoroutinefunction sees through functools.partial, so a partial of an async function is refused like the function itself. A timezone other than timezone.utc whose offset is zero is still UTC.
RELATED DOCS: vidbyte/lib/README.md (dataclasses/validation.py); docs/spec/infinite-memory-events/spec.md sections 8.5, 9.1 and 12.3; docs/spec/infinite-memory-events/test-plan.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_record_field_validation_event_options.py -q
"""

from __future__ import annotations

import functools
import math
from datetime import datetime, timedelta, timezone

import pytest

from vidbyte.lib.dataclasses.validation import RecordFieldValidator
from vidbyte.lib.errors import ConfigurationError

FIELD = "X.f"
UTC_AT = datetime(2026, 10, 16, 8, 15, 0, 123_000, tzinfo=timezone.utc)


def _field(raised: pytest.ExceptionInfo[ConfigurationError]) -> object:
    # The field a refusal names in its details.
    return raised.value.details["field"]


async def _async_sink(event: object) -> None:
    return None


class _AsyncCall:
    async def __call__(self, event: object) -> None:
        return None


class _PlainCall:
    def __call__(self, event: object) -> None:
        return None


def test_require_number_accepts_zero_only_with_allow_zero() -> None:
    """AC-37 (d), INV-38: without allow_zero, 0 is still refused; with allow_zero=True, 0 and 0.0 are returned while a negative, NaN, infinite, too large, or bool value is still refused."""
    with pytest.raises(ConfigurationError) as raised:
        RecordFieldValidator.require_number(0, FIELD, maximum=1.0)
    assert _field(raised) == FIELD
    assert RecordFieldValidator.require_number(0, FIELD, maximum=1.0, allow_zero=True) == 0
    assert RecordFieldValidator.require_number(0.0, FIELD, maximum=1.0, allow_zero=True) == 0.0
    assert RecordFieldValidator.require_number(0.5, FIELD, maximum=1.0, allow_zero=True) == 0.5
    for value in (-0.01, math.nan, math.inf, 1.5, True):
        with pytest.raises(ConfigurationError) as raised:
            RecordFieldValidator.require_number(value, FIELD, maximum=1.0, allow_zero=True)
        assert _field(raised) == FIELD, value


def test_require_utc_datetime_accepts_only_a_zero_offset_at_the_resolution() -> None:
    """AC-37 (b): a UTC time whose microseconds are a multiple of the resolution is returned; another offset, a naive time, a finer time, or a non-datetime is refused by field; the default resolution of 1 accepts any microsecond."""
    assert RecordFieldValidator.require_utc_datetime(UTC_AT, FIELD, resolution_microseconds=1_000) == UTC_AT
    zero_offset = UTC_AT.astimezone(timezone(timedelta(0), "Z"))
    assert RecordFieldValidator.require_utc_datetime(zero_offset, FIELD, resolution_microseconds=1_000) == zero_offset
    fine = UTC_AT.replace(microsecond=1)
    assert RecordFieldValidator.require_utc_datetime(fine, FIELD) == fine
    for value in (UTC_AT.astimezone(timezone(timedelta(hours=1))), UTC_AT.replace(tzinfo=None), fine, UTC_AT.isoformat()):
        with pytest.raises(ConfigurationError) as raised:
            RecordFieldValidator.require_utc_datetime(value, FIELD, resolution_microseconds=1_000)
        assert _field(raised) == FIELD, value


def test_require_callable_refuses_none_unless_optional_and_async_sinks_when_synchronous() -> None:
    """AC-37 (c), INV-36, D-27: None is refused naming the field unless optional; a non-callable is refused; with synchronous=True an async function, an object with an async __call__, and a partial of an async function are refused while print, a bound list.append, a plain __call__ object, and a lambda are returned unchanged; without synchronous an async function is accepted."""
    with pytest.raises(ConfigurationError, match=r"X\.f") as raised:
        RecordFieldValidator.require_callable(None, FIELD)
    assert _field(raised) == FIELD
    assert RecordFieldValidator.require_callable(None, FIELD, optional=True) is None
    with pytest.raises(ConfigurationError) as raised:
        RecordFieldValidator.require_callable(42, FIELD, optional=True, synchronous=True)
    assert _field(raised) == FIELD
    assert RecordFieldValidator.require_callable(_async_sink, FIELD) is _async_sink
    for sink in (_async_sink, _AsyncCall(), functools.partial(_async_sink)):
        with pytest.raises(ConfigurationError, match=r"X\.f") as raised:
            RecordFieldValidator.require_callable(sink, FIELD, optional=True, synchronous=True)
        assert _field(raised) == FIELD, sink
    for sink in (print, [].append, _PlainCall(), lambda event: None):
        assert RecordFieldValidator.require_callable(sink, FIELD, optional=True, synchronous=True) is sink
