"""FILE: vidbyte/tools/builtins/prebuilt/timestamps_durations.py

PURPOSE: Defines TimestampsDurationsToolFunctions, the eight prebuilt tools that work with Unix timestamps, fixed UTC offsets, and durations: timestamp to date and time and back, offset conversion, the time between two moments, adding a duration, writing a duration, reading a duration, and the minutes between two clock times.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the TIMESTAMPS_DURATIONS category is chosen. Builds on PrebuiltToolSupport in _support.py for UTC reading, offsets, integer text, and the argument error, and on PREBUILT_DURATION_UNIT_WORDS for duration unit words.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Time arithmetic runs on whole microseconds or milliseconds held in int, and every float that becomes exact output is read once through Decimal(repr(x)) and rounded half to even, so no result depends on float rounding or on the host's clock and time zone.
FUNCTION INVENTORY: unix_timestamp_to_datetime, datetime_to_unix_timestamp, convert_utc_offset, duration_between_datetimes, add_duration_to_datetime, format_duration, parse_duration_text, and minutes_between_times are the tools; _rounded_units rounds a float to whole units of a scale; _duration_parts and _styled_duration split and write a duration; _iso_duration_seconds, _clock_duration_seconds, and _phrase_duration_seconds read the three duration forms; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new timestamp or duration tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.11, and its entry in tool_functions. A new duration unit word goes into PREBUILT_DURATION_UNIT_WORDS, never into a local table.
WHAT NOT TO DO IN THIS FILE: 1. Do not read the clock or the local time zone; every moment comes from the arguments. 2. Do not build a naive datetime or use timedelta(seconds=float), round(), or Decimal(x) on a float; scale Decimal(repr(x)) and round once. 3. Do not convert an aware datetime through UTC to reach another offset, because the UTC step can leave the supported years even when the result does not.
KNOWN EDGE CASES: A negative timestamp works on every platform because the result is the epoch plus a timedelta. A duration is rounded as one total before it is split, so 59.9996 seconds is one minute and no part ever reaches 60. A duration that rounds to zero has no minus sign. Time zones are fixed offsets only, so no tool applies daylight-saving rules.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.11, section 9.2 items 11 and 17); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_time.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_DURATION_UNIT_WORDS,
    PREBUILT_FINANCE_PRECISION,
    PREBUILT_MAX_DATE_OFFSET,
    PREBUILT_MAX_DURATION_SECONDS,
    PREBUILT_MAX_PHRASE_CHARS,
    PREBUILT_MAX_UTC_OFFSET_CHARS,
    PREBUILT_UTC_OFFSET_PATTERN,
)
from vidbyte.lib.enums.prebuilt_tools import DurationStyle, TimestampUnit, Weekday
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_WEEKDAYS = tuple(Weekday)

_MICROSECONDS_PER_SECOND = 1_000_000
_MICROSECONDS_PER_MINUTE = 60 * _MICROSECONDS_PER_SECOND
_MICROSECONDS_PER_HOUR = 60 * _MICROSECONDS_PER_MINUTE
_MICROSECONDS_PER_DAY = 24 * _MICROSECONDS_PER_HOUR
_MILLISECONDS_PER_SECOND = 1_000
_MILLISECONDS_PER_MINUTE = 60 * _MILLISECONDS_PER_SECOND
_MILLISECONDS_PER_HOUR = 60 * _MILLISECONDS_PER_MINUTE
_MILLISECONDS_PER_DAY = 24 * _MILLISECONDS_PER_HOUR
_HOURS_PER_DAY = 24

# How many microseconds one timestamp unit holds, as an exact Decimal.
_MICROSECONDS_PER_UNIT = MappingProxyType(
    {
        TimestampUnit.SECONDS: Decimal(_MICROSECONDS_PER_SECOND),
        TimestampUnit.MILLISECONDS: Decimal(_MICROSECONDS_PER_SECOND // _MILLISECONDS_PER_SECOND),
        TimestampUnit.MICROSECONDS: Decimal(1),
        TimestampUnit.NANOSECONDS: Decimal("0.001"),
    }
)
# Each unit as (multiplier, divisor) applied to whole microseconds.
_UNIT_FROM_MICROSECONDS = MappingProxyType(
    {
        TimestampUnit.SECONDS: (1, _MICROSECONDS_PER_SECOND),
        TimestampUnit.MILLISECONDS: (1, _MICROSECONDS_PER_SECOND // _MILLISECONDS_PER_SECOND),
        TimestampUnit.MICROSECONDS: (1, 1),
        TimestampUnit.NANOSECONDS: (_MILLISECONDS_PER_SECOND, 1),
    }
)

_COMPACT_UNIT_LETTERS = ("d", "h", "m", "s")
_ISO_UNIT_LETTERS = ("D", "H", "M", "S")
_LONG_UNIT_NAMES = ("day", "hour", "minute", "second")

# The duration grammar: a number may carry a decimal fraction, ISO 8601
# parts come in their fixed order, and unit phrases may be separated by
# spaces, commas, or the word and.
_DURATION_NUMBER = r"(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
_ISO_DURATION = re.compile(
    rf"P(?:(?P<years>{_DURATION_NUMBER})Y)?(?:(?P<months>{_DURATION_NUMBER})M)?(?:(?P<week>{_DURATION_NUMBER})W)?(?:(?P<day>{_DURATION_NUMBER})D)?"
    + rf"(?:T(?=[0-9.])(?:(?P<hour>{_DURATION_NUMBER})H)?(?:(?P<minute>{_DURATION_NUMBER})M)?(?:(?P<second>{_DURATION_NUMBER})S)?)?",
    re.IGNORECASE,
)
_ISO_PART_NAMES = ("week", "day", "hour", "minute", "second")
_CLOCK_DURATION = re.compile(r"(?P<hour>[0-9]+):(?P<minute>[0-5][0-9])(?::(?P<second>[0-5][0-9](?:\.[0-9]+)?))?")
_PHRASE_PART = re.compile(
    rf"(?P<separator>\s*,\s*(?:and\s+)?|\s+and\s+|\s*)(?P<number>{_DURATION_NUMBER})\s*(?P<unit>[a-z]+)",
    re.IGNORECASE,
)
# The whole phrase holds at most PREBUILT_MAX_PHRASE_CHARS characters,
# so every exact product and sum of its parts fits in twice as many
# digits and the Decimal sum never rounds.
_PHRASE_SUM_DIGITS = 2 * PREBUILT_MAX_PHRASE_CHARS

_DATETIME_PARAMETER_DESCRIPTION = "A moment in time written as an ISO 8601 date and time, with optional seconds and fractional seconds. A fixed UTC offset or the letter Z may follow the time. A value written without an offset is read as UTC. Years run from 1 through 9999."
_DURATION_PART_DESCRIPTION = "The whole number of {unit} to add, which may be negative to subtract. Each one is a fixed amount of elapsed time, so daylight-saving changes are ignored. The value must be between minus one million and one million. The default is 0."
_OUT_OF_RANGE_EXPECTED = "inputs whose result falls in years 1 through 9999"


class TimestampsDurationsToolFunctions:
    """The timestamps_durations category: Unix timestamps, fixed UTC offsets, and durations."""

    @staticmethod
    def unix_timestamp_to_datetime(
        timestamp: Annotated[float, Field(description="The Unix timestamp to convert, counted in the chosen unit from the start of 1970 in UTC. It may be negative for moments before 1970 and may carry a fractional part. It is rounded half to even to whole microseconds, and digits beyond what a float holds are lost. A result outside years 1 through 9999 fails with an error.", allow_inf_nan=False)],
        unit: Annotated[TimestampUnit, Field(description="The unit the timestamp counts in: seconds, milliseconds, microseconds, or nanoseconds. Most systems count seconds, while JavaScript and many logs count milliseconds. Nanoseconds are rounded to whole microseconds. The default is seconds.")] = TimestampUnit.SECONDS,
        utc_offset: Annotated[str, Field(description="The fixed UTC offset at which to show the result, written as Z or as a plus or minus sign followed by HH:MM. Hours run from 00 to 23 and minutes from 00 to 59. Daylight-saving rules are not applied, because the offset is fixed. The default is UTC itself.", pattern=PREBUILT_UTC_OFFSET_PATTERN, max_length=PREBUILT_MAX_UTC_OFFSET_CHARS)] = "+00:00",
    ) -> PrebuiltToolOutput:
        """Convert a Unix timestamp into an ISO 8601 date and time, its date, its time of day, and its weekday, shown at a fixed UTC offset. Use it to read epoch values from logs, databases, and APIs instead of working out calendar dates by hand. The timestamp may be in seconds, milliseconds, microseconds, or nanoseconds, may be negative or fractional, and is rounded half to even to whole microseconds. A result outside years 1 through 9999 fails with an error naming timestamp."""
        # Scale the timestamp's shortest text exactly to microseconds
        # and round it once, half to even.
        zone = PrebuiltToolSupport.parse_utc_offset(utc_offset)
        microseconds = TimestampsDurationsToolFunctions._rounded_units(timestamp, _MICROSECONDS_PER_UNIT[unit])

        # Add the microseconds and the offset to the epoch, then label
        # the wall-clock result with the offset; years outside 1 through
        # 9999 overflow here.
        try:
            local = (_EPOCH + (timedelta(microseconds=microseconds) + zone.utcoffset(None))).replace(tzinfo=zone)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("timestamp", "the moment falls outside years 1 through 9999", _OUT_OF_RANGE_EXPECTED) from exc
        return {"datetime": local.isoformat(), "date": local.date().isoformat(), "time": local.time().isoformat(), "weekday": _WEEKDAYS[local.weekday()].value}

    @staticmethod
    def datetime_to_unix_timestamp(
        moment: Annotated[datetime, Field(description=_DATETIME_PARAMETER_DESCRIPTION)],
        unit: Annotated[TimestampUnit, Field(description="The unit of the returned timestamp: seconds, milliseconds, microseconds, or nanoseconds. The value is floored to a whole unit, so a moment before 1970 moves toward the past. Nanoseconds are the microseconds times one thousand, because the input holds no finer detail. The default is seconds.")] = TimestampUnit.SECONDS,
    ) -> PrebuiltToolOutput:
        """Convert an ISO 8601 date and time into a Unix timestamp in seconds, milliseconds, microseconds, or nanoseconds. Use it to produce epoch values for APIs, databases, or log queries. The value is floored to a whole unit and returned as integer text, because nanosecond values pass the exact integer range of a float. A value without an offset is read as UTC, and the tool has no failure case beyond input validation."""
        # Count whole microseconds since the epoch, then floor them to
        # the chosen unit.
        elapsed = PrebuiltToolSupport.as_utc(moment) - _EPOCH
        microseconds = elapsed // timedelta(microseconds=1)
        multiplier, divisor = _UNIT_FROM_MICROSECONDS[unit]
        return {"timestamp": PrebuiltToolSupport.integer_text(microseconds * multiplier // divisor, "moment")}

    @staticmethod
    def convert_utc_offset(
        moment: Annotated[datetime, Field(description=_DATETIME_PARAMETER_DESCRIPTION)],
        to_offset: Annotated[str, Field(description="The fixed UTC offset to show the moment at, written as Z or as a plus or minus sign followed by HH:MM. Hours run from 00 to 23 and minutes from 00 to 59. Daylight-saving rules are not applied, because the offset is fixed. A result outside years 1 through 9999 fails with an error.", pattern=PREBUILT_UTC_OFFSET_PATTERN, max_length=PREBUILT_MAX_UTC_OFFSET_CHARS)],
    ) -> PrebuiltToolOutput:
        """Show a moment in time at a different fixed UTC offset, with the new date, the new time of day, and the change in calendar day. Use it to translate a meeting time or a log timestamp into another region's clock when that region's offset is known. Offsets are fixed, so daylight-saving rules are not applied, and day_shift is the new local date minus the original local date in days. A result outside years 1 through 9999 fails with an error naming to_offset."""
        # Move the wall clock by the difference between the two offsets
        # instead of passing through UTC, so only the result's own year
        # can overflow.
        original = PrebuiltToolSupport.as_utc(moment)
        zone = PrebuiltToolSupport.parse_utc_offset(to_offset)
        shift = zone.utcoffset(None) - (original.utcoffset() or timedelta())
        try:
            local = (original + shift).replace(tzinfo=zone)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("to_offset", "the moment at that offset falls outside years 1 through 9999", _OUT_OF_RANGE_EXPECTED) from exc
        return {"datetime": local.isoformat(), "date": local.date().isoformat(), "time": local.time().isoformat(), "day_shift": (local.date() - original.date()).days}

    @staticmethod
    def duration_between_datetimes(
        start: Annotated[datetime, Field(description="The moment the duration starts, written as an ISO 8601 date and time. A fixed UTC offset or the letter Z may follow the time, and offsets are honored when measuring. A value written without an offset is read as UTC. A start later than the end gives a negative total.")],
        end: Annotated[datetime, Field(description="The moment the duration ends, written as an ISO 8601 date and time. A fixed UTC offset or the letter Z may follow the time, and offsets are honored when measuring. A value written without an offset is read as UTC. An end earlier than the start gives a negative total.")],
    ) -> PrebuiltToolOutput:
        """Measure the exact time between two moments as signed total seconds and as days, hours, minutes, and seconds. Use it for elapsed times, the length of an event, or the gap between two timestamps. UTC offsets are honored, a value without an offset is read as UTC, and the parts break down the absolute difference while negative tells whether the end comes first. The tool has no failure case beyond input validation."""
        # Measure the signed difference in whole microseconds, then
        # split its absolute value into days, hours, minutes, and
        # seconds.
        elapsed = PrebuiltToolSupport.as_utc(end) - PrebuiltToolSupport.as_utc(start)
        microseconds = elapsed // timedelta(microseconds=1)
        days, rest = divmod(abs(microseconds), _MICROSECONDS_PER_DAY)
        hours, rest = divmod(rest, _MICROSECONDS_PER_HOUR)
        minutes, rest = divmod(rest, _MICROSECONDS_PER_MINUTE)
        return {
            "total_seconds": microseconds / _MICROSECONDS_PER_SECOND,
            "days": days,
            "hours": hours,
            "minutes": minutes,
            "seconds": rest / _MICROSECONDS_PER_SECOND,
            "negative": microseconds < 0,
        }

    @staticmethod
    def add_duration_to_datetime(
        moment: Annotated[datetime, Field(description=_DATETIME_PARAMETER_DESCRIPTION)],
        days: Annotated[int, Field(description=_DURATION_PART_DESCRIPTION.format(unit="days"), ge=-PREBUILT_MAX_DATE_OFFSET, le=PREBUILT_MAX_DATE_OFFSET)] = 0,
        hours: Annotated[int, Field(description=_DURATION_PART_DESCRIPTION.format(unit="hours"), ge=-PREBUILT_MAX_DATE_OFFSET, le=PREBUILT_MAX_DATE_OFFSET)] = 0,
        minutes: Annotated[int, Field(description=_DURATION_PART_DESCRIPTION.format(unit="minutes"), ge=-PREBUILT_MAX_DATE_OFFSET, le=PREBUILT_MAX_DATE_OFFSET)] = 0,
        seconds: Annotated[float, Field(description="The number of seconds to add, which may be negative to subtract and may carry a fractional part. It is rounded half to even to whole microseconds before it is added. Its magnitude must be at most one trillion. The default is 0.", allow_inf_nan=False, ge=-PREBUILT_MAX_DURATION_SECONDS, le=PREBUILT_MAX_DURATION_SECONDS)] = 0.0,
    ) -> PrebuiltToolOutput:
        """Add or subtract days, hours, minutes, and seconds from a moment and return the resulting date and time. Use it to compute deadlines, expiry times, or reminders relative to a timestamp. The arithmetic is elapsed time that keeps the input's UTC offset, so it is not daylight-saving aware, and fractional seconds are rounded half to even to whole microseconds. A result outside years 1 through 9999 fails with an error naming days."""
        # Round the seconds exactly to microseconds, then add the whole
        # duration to the moment at its own offset.
        microseconds = TimestampsDurationsToolFunctions._rounded_units(seconds, Decimal(_MICROSECONDS_PER_SECOND))
        try:
            result = PrebuiltToolSupport.as_utc(moment) + timedelta(days=days, hours=hours, minutes=minutes, microseconds=microseconds)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("days", "the result falls outside years 1 through 9999", _OUT_OF_RANGE_EXPECTED) from exc
        return {"datetime": result.isoformat(), "date": result.date().isoformat(), "time": result.time().isoformat()}

    @staticmethod
    def format_duration(
        seconds: Annotated[float, Field(description="The length of the duration in seconds, which may be negative and may carry a fractional part. It is rounded half to even to whole milliseconds before it is split into parts. Its magnitude must be at most one trillion. A negative value gets a minus sign unless it rounds to zero.", allow_inf_nan=False, ge=-PREBUILT_MAX_DURATION_SECONDS, le=PREBUILT_MAX_DURATION_SECONDS)],
        style: Annotated[DurationStyle, Field(description="How to write the duration. Compact writes unit letters, long writes English words with commas, clock writes hours, minutes, and seconds between colons, and iso8601 writes an ISO 8601 duration that uses days at most. Zero parts are left out in every style except clock. The default is compact.")] = DurationStyle.COMPACT,
    ) -> PrebuiltToolOutput:
        """Write a number of seconds as a readable duration in compact, long, clock, or ISO 8601 style. Use it to present an elapsed time or a timeout to people, or to produce an ISO 8601 duration string. The value is rounded half to even to whole milliseconds before it is split into days, hours, minutes, and seconds, and the seconds show up to three fractional digits. The tool has no failure case beyond the bound on seconds."""
        # Round the whole value to milliseconds first, so no part needs
        # a carry, then split and write the absolute value.
        milliseconds = TimestampsDurationsToolFunctions._rounded_units(seconds, Decimal(_MILLISECONDS_PER_SECOND))
        text = TimestampsDurationsToolFunctions._styled_duration(TimestampsDurationsToolFunctions._duration_parts(abs(milliseconds)), style)
        return {"text": f"-{text}" if milliseconds < 0 else text}

    @staticmethod
    def parse_duration_text(
        text: Annotated[str, Field(description="The duration to read, written as an ISO 8601 duration, a clock time, or numbers with English unit words. An ISO 8601 duration may use weeks, days, hours, minutes, and seconds, but not years or months. A clock time is hours and minutes with optional seconds, and unit phrases may be separated by spaces, commas, and the word and. The text must hold between 1 and 200 characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Read a duration written as an ISO 8601 duration, a clock time, or English unit phrases, and return its total length in seconds with its ISO 8601 form. Use it to turn a length of time written by a person into an exact number before doing arithmetic with it. Weeks, days, hours, minutes, seconds, and milliseconds are understood, every number may have a decimal fraction, and the parts are summed exactly. Years, months, unknown units, and any other text fail with an error naming text."""
        # Try the ISO 8601 form, then the clock form, then unit phrases.
        stripped = text.strip()
        total = TimestampsDurationsToolFunctions._iso_duration_seconds(stripped)
        if total is None:
            total = TimestampsDurationsToolFunctions._clock_duration_seconds(stripped)
        if total is None:
            total = TimestampsDurationsToolFunctions._phrase_duration_seconds(stripped)
        if total is None:
            expected = "an ISO 8601 duration without years or months, a clock time such as hours and minutes with optional seconds, or numbers with units from weeks down to milliseconds"
            raise PrebuiltToolSupport.argument_error("text", "the text is not a duration in any accepted form", expected)

        # Convert the exact sum to a float once and write that float as
        # format_duration writes it in the iso8601 style.
        total_seconds = float(total)
        milliseconds = TimestampsDurationsToolFunctions._rounded_units(total_seconds, Decimal(_MILLISECONDS_PER_SECOND))
        iso8601 = TimestampsDurationsToolFunctions._styled_duration(TimestampsDurationsToolFunctions._duration_parts(milliseconds), DurationStyle.ISO8601)
        return {"total_seconds": total_seconds, "iso8601": iso8601}

    @staticmethod
    def minutes_between_times(
        start_time: Annotated[time, Field(description="The clock time to count from, written as hours and minutes with optional seconds and fractional seconds. It is a local time of day with no date attached. A time that carries a UTC offset fails with an error. The hour must be between 0 and 23.")],
        end_time: Annotated[time, Field(description="The clock time to count to, written as hours and minutes with optional seconds and fractional seconds. When it is earlier than the start time, the count wraps past midnight. A time that carries a UTC offset fails with an error. The hour must be between 0 and 23.")],
    ) -> PrebuiltToolOutput:
        """Count the minutes from one clock time to another, wrapping past midnight when the end is earlier than the start. Use it for shift lengths, opening hours, and overnight spans when only the times of day are known. The result is a float that keeps fractional seconds, and wrapped tells whether 24 hours were added. A time that carries a UTC offset fails with an error naming that time, checking start_time first."""
        # Refuse a time with an offset, checking the start first.
        for name, moment in (("start_time", start_time), ("end_time", end_time)):
            if moment.utcoffset() is not None:
                raise PrebuiltToolSupport.argument_error(name, "the time carries a UTC offset", "a local time of day without an offset")

        # Count microseconds since midnight for each time, then add a
        # day when the end comes before the start.
        start_count, end_count = (_MICROSECONDS_PER_HOUR * moment.hour + _MICROSECONDS_PER_MINUTE * moment.minute + _MICROSECONDS_PER_SECOND * moment.second + moment.microsecond for moment in (start_time, end_time))
        wrapped = end_count < start_count
        span = end_count - start_count + (_MICROSECONDS_PER_DAY if wrapped else 0)
        return {"minutes": span / _MICROSECONDS_PER_MINUTE, "wrapped": wrapped}

    @staticmethod
    def _rounded_units(value: float, scale: Decimal) -> int:
        """Scale a float's shortest text exactly by scale and round it once, half to even, to a whole number."""
        with PrebuiltToolSupport.decimal_context(PREBUILT_FINANCE_PRECISION):
            return int((Decimal(repr(value)) * scale).to_integral_value())

    @staticmethod
    def _duration_parts(milliseconds: int) -> tuple[int, int, int, int]:
        """Split a non-negative number of milliseconds into days, hours, minutes, and the milliseconds left in the minute."""
        days, rest = divmod(milliseconds, _MILLISECONDS_PER_DAY)
        hours, rest = divmod(rest, _MILLISECONDS_PER_HOUR)
        minutes, rest = divmod(rest, _MILLISECONDS_PER_MINUTE)
        return days, hours, minutes, rest

    @staticmethod
    def _styled_duration(parts: tuple[int, int, int, int], style: DurationStyle) -> str:
        """Write duration parts without a sign in one style, leaving out zero parts except in the clock style."""
        days, hours, minutes, rest = parts
        whole, fraction = divmod(rest, _MILLISECONDS_PER_SECOND)
        fraction_text = f".{fraction:03d}".rstrip("0") if fraction else ""
        texts = (str(days), str(hours), str(minutes), f"{whole}{fraction_text}")
        present = [(index, texts[index]) for index, amount in enumerate(parts) if amount]
        match style:
            case DurationStyle.CLOCK:
                return f"{days * _HOURS_PER_DAY + hours}:{minutes:02d}:{whole:02d}{fraction_text}"
            case DurationStyle.LONG:
                words = [f"{amount} {_LONG_UNIT_NAMES[index]}{'' if amount == '1' else 's'}" for index, amount in present]
                return ", ".join(words) or "0 seconds"
            case DurationStyle.ISO8601:
                if not present:
                    return "PT0S"
                date_part = "".join(f"{amount}D" for index, amount in present if index == 0)
                time_part = "".join(f"{amount}{_ISO_UNIT_LETTERS[index]}" for index, amount in present if index > 0)
                return f"P{date_part}" + (f"T{time_part}" if time_part else "")
            case _:
                return " ".join(f"{amount}{_COMPACT_UNIT_LETTERS[index]}" for index, amount in present) or "0s"

    @staticmethod
    def _iso_duration_seconds(text: str) -> Decimal | None:
        """Read an ISO 8601 duration with week, day, hour, minute, and second parts as exact seconds, or return None."""
        match = _ISO_DURATION.fullmatch(text)
        if match is None or not any(match.group(name) for name in _ISO_PART_NAMES + ("years", "months")):
            return None
        if match.group("years") or match.group("months"):
            problem = "the ISO 8601 duration has a year or month part, whose length in seconds varies"
            raise PrebuiltToolSupport.argument_error("text", problem, "an ISO 8601 duration that uses weeks, days, hours, minutes, and seconds only")
        with PrebuiltToolSupport.decimal_context(_PHRASE_SUM_DIGITS):
            return sum((Decimal(match.group(name)) * Decimal(PREBUILT_DURATION_UNIT_WORDS[name]) for name in _ISO_PART_NAMES if match.group(name)), Decimal(0))

    @staticmethod
    def _clock_duration_seconds(text: str) -> Decimal | None:
        """Read an H:MM or H:MM:SS clock duration, seconds possibly fractional, as exact seconds, or return None."""
        match = _CLOCK_DURATION.fullmatch(text)
        if match is None:
            return None
        with PrebuiltToolSupport.decimal_context(_PHRASE_SUM_DIGITS):
            return sum((Decimal(match.group(name)) * Decimal(PREBUILT_DURATION_UNIT_WORDS[name]) for name in ("hour", "minute", "second") if match.group(name)), Decimal(0))

    @staticmethod
    def _phrase_duration_seconds(text: str) -> Decimal | None:
        """Read numbers with unit words, joined by spaces, commas, or and, as exact seconds, or return None."""
        total = Decimal(0)
        position = 0
        with PrebuiltToolSupport.decimal_context(_PHRASE_SUM_DIGITS):
            while position < len(text):
                # Each part is an optional separator, a number, and a
                # unit word; the first part may not start with one.
                match = _PHRASE_PART.match(text, position)
                if match is None or (position == 0 and match.group("separator")):
                    return None
                factor = PREBUILT_DURATION_UNIT_WORDS.get(match.group("unit").lower())
                if factor is None:
                    return None
                total += Decimal(match.group("number")) * Decimal(factor)
                position = match.end()
        return total if position else None

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.unix_timestamp_to_datetime,
            cls.datetime_to_unix_timestamp,
            cls.convert_utc_offset,
            cls.duration_between_datetimes,
            cls.add_duration_to_datetime,
            cls.format_duration,
            cls.parse_duration_text,
            cls.minutes_between_times,
        )


__all__ = ["TimestampsDurationsToolFunctions"]
