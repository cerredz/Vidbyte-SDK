"""FILE: vidbyte/tools/builtins/prebuilt/scheduling.py

PURPOSE: Defines SchedulingToolFunctions, the eight prebuilt scheduling tools: business days between two dates, adding business days, listing the dates of a range, counting a weekday in a range, recurring dates, merging time intervals, finding common free slots, and sorting date strings written in mixed formats.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the SCHEDULING category is chosen. Builds on PrebuiltToolSupport in _support.py for the item cap, paired lists, UTC reading of naive datetimes, fixed offsets, written dates, and the argument error.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Business-day work runs on proleptic ordinals with whole-week arithmetic and a sorted holiday list searched by bisection, and recurrence and range counts are arithmetic, so even a span from year 1 to year 9999 finishes at once while only the listed dates are built.
FUNCTION INVENTORY: business_days_between, add_business_days, list_dates_in_range, count_weekday_occurrences, generate_recurring_dates, merge_time_intervals, find_common_free_slots, and sort_date_strings are the tools; _working_calendar reads the weekend and the holidays; _count_business_days and _find_business_ordinal do the business-day arithmetic; _steps_until and _recurrence_date count and build recurrence dates; _aware_spans, _merge_spans, _free_gaps, and _shown_spans read, merge, invert, and write time spans; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new scheduling tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.10, and its entry in tool_functions. Business-day rules change in _working_calendar and the two arithmetic helpers together, so the count and the move always agree.
WHAT NOT TO DO IN THIS FILE: 1. Do not loop day by day over a business-day range or a recurrence to count it; counts stay arithmetic so year-long and millennium-long spans stay instant. 2. Do not convert a datetime to UTC before comparing it; aware datetimes compare across offsets, and a conversion near year 1 or year 9999 can overflow. 3. Do not build naive datetimes; inputs without an offset go through PrebuiltToolSupport.as_utc. 4. Do not iterate a set of holidays to build output; sort it first.
KNOWN EDGE CASES: The weekday of an ordinal is the ordinal minus one modulo seven, because the first of January of year 1 is a Monday. A business-day move may run past the end of the calendar, which fails naming business_days. A time shown at an output offset can fall outside years 1 to 9999 and fails naming output_offset. Intervals that only touch are merged, and a gap exactly as long as the minimum is kept.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.10, section 9.2 items 11, 12, and 13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_time.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import bisect
import calendar
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_BUSINESS_DAYS,
    PREBUILT_MAX_DATE_SPAN_DAYS,
    PREBUILT_MAX_FREE_SLOT_MINUTES,
    PREBUILT_MAX_HOLIDAYS,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_PHRASE_CHARS,
    PREBUILT_MAX_RECURRENCE_STEP,
    PREBUILT_MAX_RESULT_ITEMS,
    PREBUILT_MAX_UTC_OFFSET_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import RecurrenceFrequency, Weekday
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_DAYS_IN_WEEK = 7
_MONTHS_IN_YEAR = 12
_FIRST_ORDINAL = date.min.toordinal()
_LAST_ORDINAL = date.max.toordinal()
_ONE_MINUTE = timedelta(minutes=1)
_ONE_MICROSECOND = timedelta(microseconds=1)
_MICROSECONDS_PER_MINUTE = _ONE_MINUTE // _ONE_MICROSECOND
_UTC_OFFSET_PATTERN = r"^(Z|[+-](0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])$"
_DEFAULT_WEEKEND = (Weekday.SATURDAY, Weekday.SUNDAY)
_EVERY_WEEKDAY = frozenset(range(_DAYS_IN_WEEK))
_WEEKDAY_NUMBERS = MappingProxyType({member: number for number, member in enumerate(Weekday)})
_FREQUENCY_STEPS = MappingProxyType({RecurrenceFrequency.DAILY: (1, 0), RecurrenceFrequency.WEEKLY: (_DAYS_IN_WEEK, 0), RecurrenceFrequency.MONTHLY: (0, 1), RecurrenceFrequency.YEARLY: (0, _MONTHS_IN_YEAR)})
_END_BEFORE_START = "the end date comes before the start date"
_END_ON_OR_AFTER_START = "an end date on or after the start date"

_RANGE_START_DESCRIPTION = "The first date of the range, written as an ISO calendar date in the YYYY-MM-DD form. The range includes this date itself. It must be a real day of the proleptic Gregorian calendar between year 1 and year 9999. A day that does not exist in its month fails validation."
_RANGE_END_DESCRIPTION = "The last date of the range, written as an ISO calendar date in the YYYY-MM-DD form. The range includes this date itself. It must not come before the start date, or the tool fails with an error naming this parameter. A day that does not exist in its month fails validation."
_HOLIDAYS_DESCRIPTION = "Dates that are not working days even though they fall on a working weekday, each written as an ISO calendar date in the YYYY-MM-DD form. A holiday on a weekend day has no extra effect. A date listed more than once counts once. The list may hold at most 1,000 dates."
_WEEKEND_DESCRIPTION = "The weekdays that are never working days, written as lowercase English weekday names. The default is saturday and sunday. Repeated names count once, and the list may hold at most seven names. Marking all seven days as weekend fails with an error naming this parameter."
_OUTPUT_OFFSET_DESCRIPTION = "The fixed UTC offset at which the result times are written, given as Z or as a plus or minus sign followed by HH:MM. The offset only changes how the times are written, never which instants they are. Hours run from 00 to 23 and minutes from 00 to 59. The default is UTC itself, written with a zero offset."
_DAY_FIRST_DESCRIPTION = "Whether a numeric date whose first two parts could both be the month is read day first. When false, the first part is the month, as in the convention of the United States. A part greater than twelve is always the day, whatever this setting says. The default is false."


class SchedulingToolFunctions:
    """The scheduling category: business days, date ranges, recurrences, time intervals, free slots, and date sorting."""

    @staticmethod
    def business_days_between(
        start_date: Annotated[date, Field(description=_RANGE_START_DESCRIPTION)],
        end_date: Annotated[date, Field(description="The last date of the range, written as an ISO calendar date in the YYYY-MM-DD form. The range includes this date itself. It may come before the start date, which makes the count negative. A day that does not exist in its month fails validation.")],
        holidays: Annotated[tuple[date, ...], Field(description=_HOLIDAYS_DESCRIPTION, max_length=PREBUILT_MAX_HOLIDAYS)] = (),
        weekend_days: Annotated[tuple[Weekday, ...], Field(description=_WEEKEND_DESCRIPTION, max_length=_DAYS_IN_WEEK)] = _DEFAULT_WEEKEND,
    ) -> PrebuiltToolOutput:
        """Count the working days between two dates with both ends included, skipping weekend days and listed holidays, like the spreadsheet NETWORKDAYS function. Use it for delivery times, notice periods, and service levels counted in business days. Holidays on weekend days or outside the range are ignored, duplicates count once, and the count is negative when the end comes before the start. The count uses whole-week arithmetic, so long ranges are instant, and marking all seven days as weekend fails with an error naming weekend_days."""
        # Read the weekend and keep only holidays on working weekdays.
        weekend, holiday_ordinals = SchedulingToolFunctions._working_calendar(holidays, weekend_days)

        # Count over the range in date order, then give the count the
        # sign of the direction from start to end.
        first, last = sorted((start_date, end_date))
        count = SchedulingToolFunctions._count_business_days(first.toordinal(), last.toordinal(), weekend, holiday_ordinals)
        return {"business_days": -count if end_date < start_date else count}

    @staticmethod
    def add_business_days(
        start_date: Annotated[date, Field(description="The date to move from, written as an ISO calendar date in the YYYY-MM-DD form. It is not counted itself, whether or not it is a working day. It must be a real day between year 1 and year 9999. A day that does not exist in its month fails validation.")],
        business_days: Annotated[int, Field(description="How many working days to move, forward when positive and backward when negative. The start date itself is not counted, so a move of one lands on the next working day. Zero returns the start date when it is a working day and the next working day otherwise. It must be between minus 100,000 and 100,000, and a result outside years 1 to 9999 fails with an error naming this parameter.", ge=-PREBUILT_MAX_BUSINESS_DAYS, le=PREBUILT_MAX_BUSINESS_DAYS)],
        holidays: Annotated[tuple[date, ...], Field(description=_HOLIDAYS_DESCRIPTION, max_length=PREBUILT_MAX_HOLIDAYS)] = (),
        weekend_days: Annotated[tuple[Weekday, ...], Field(description=_WEEKEND_DESCRIPTION, max_length=_DAYS_IN_WEEK)] = _DEFAULT_WEEKEND,
    ) -> PrebuiltToolOutput:
        """Move a date forward or backward by a number of working days, skipping weekend days and listed holidays. Use it for due dates and deadlines stated in business days. The start date itself is not counted, and zero returns the start date when it is a working day or the next working day otherwise. Marking all seven days as weekend fails with an error naming weekend_days, and a result outside years 1 to 9999 fails with an error naming business_days."""
        # Read the weekend and keep only holidays on working weekdays.
        weekend, holiday_ordinals = SchedulingToolFunctions._working_calendar(holidays, weekend_days)

        # The start is not counted, so a move begins one day away in
        # its direction; zero looks for a working day from the start.
        step = -1 if business_days < 0 else 1
        base = start_date.toordinal() + (0 if business_days == 0 else step)
        found = SchedulingToolFunctions._find_business_ordinal(base, max(abs(business_days), 1), step, weekend, holiday_ordinals)

        # A result past either end of the calendar has no date to show.
        if not _FIRST_ORDINAL <= found <= _LAST_ORDINAL:
            raise PrebuiltToolSupport.argument_error("business_days", "the resulting date falls outside years 1 to 9999", "a move that keeps the date between years 1 and 9999")
        return {"date": date.fromordinal(found).isoformat()}

    @staticmethod
    def list_dates_in_range(
        start_date: Annotated[date, Field(description=_RANGE_START_DESCRIPTION)],
        end_date: Annotated[date, Field(description=_RANGE_END_DESCRIPTION)],
        step_days: Annotated[int, Field(description="How many days apart consecutive dates are, counted from the start date. A step of one lists every day of the range. It must be between 1 and 36,600. The end date appears only when a step lands on it exactly.", ge=1, le=PREBUILT_MAX_DATE_SPAN_DAYS)] = 1,
        weekdays: Annotated[tuple[Weekday, ...], Field(description="The weekdays to keep, written as lowercase English weekday names. An empty list keeps every date of the series. Repeated names count once, and the list may hold at most seven names. The filter applies after stepping, so it never changes which dates the step produces.", max_length=_DAYS_IN_WEEK)] = (),
    ) -> PrebuiltToolOutput:
        """List the dates from a start date to an end date at a fixed step in days, optionally keeping only chosen weekdays. Use it to enumerate the days of a schedule or to see exactly which dates a range holds. Both ends are included, at most 1,000 dates are listed, and count covers every date that matches. An end date before the start date, or a range longer than 36,600 days, fails with an error naming end_date."""
        # Refuse a backward range and one longer than the span cap.
        span = (end_date - start_date).days
        if span < 0:
            raise PrebuiltToolSupport.argument_error("end_date", _END_BEFORE_START, _END_ON_OR_AFTER_START)
        if span > PREBUILT_MAX_DATE_SPAN_DAYS:
            raise PrebuiltToolSupport.argument_error("end_date", f"the range spans {span} days", f"a range of at most {PREBUILT_MAX_DATE_SPAN_DAYS} days")

        # Count the matching dates arithmetically: the weekday of a
        # stepped date repeats every seven steps, so each of the first
        # seven steps stands for every seventh step after it.
        wanted = frozenset(_WEEKDAY_NUMBERS[day] for day in weekdays) or _EVERY_WEEKDAY
        steps = span // step_days + 1
        first_weekday = start_date.weekday()
        count = sum((steps - 1 - offset) // _DAYS_IN_WEEK + 1 for offset in range(min(steps, _DAYS_IN_WEEK)) if (first_weekday + offset * step_days) % _DAYS_IN_WEEK in wanted)

        # List the matching dates lazily up to the item cap.
        series = (start_date + timedelta(days=index * step_days) for index in range(steps))
        dates, truncated = PrebuiltToolSupport.cap_items(day.isoformat() for day in series if day.weekday() in wanted)
        return {"dates": dates, "count": count, "truncated": truncated}

    @staticmethod
    def count_weekday_occurrences(
        start_date: Annotated[date, Field(description=_RANGE_START_DESCRIPTION)],
        end_date: Annotated[date, Field(description=_RANGE_END_DESCRIPTION)],
        weekday: Annotated[Weekday, Field(description="The day of the week to count, written as a lowercase English weekday name. Every day from monday to sunday is accepted, and abbreviations are not. Both ends of the range are checked. Any other value fails validation.")],
    ) -> PrebuiltToolOutput:
        """Count how many times a weekday occurs between two dates, with both ends included. Use it to count meetings, paydays, or other weekly events across a range. The count is computed arithmetically, so even the full range from year 1 to year 9999 is instant. An end date before the start date fails with an error naming end_date."""
        days = (end_date - start_date).days + 1
        if days <= 0:
            raise PrebuiltToolSupport.argument_error("end_date", _END_BEFORE_START, _END_ON_OR_AFTER_START)
        # The first match sits this many days after the start, and every
        # seventh day after it matches again.
        first_match = (_WEEKDAY_NUMBERS[weekday] - start_date.weekday()) % _DAYS_IN_WEEK
        return {"count": 0 if first_match >= days else (days - 1 - first_match) // _DAYS_IN_WEEK + 1}

    @staticmethod
    def generate_recurring_dates(
        start_date: Annotated[date, Field(description="The first date of the recurrence, written as an ISO calendar date in the YYYY-MM-DD form. It is always the first date listed unless until_date comes before it. Monthly and yearly dates keep the day of the month of this date, clamped in shorter months. It must be a real day between year 1 and year 9999.")],
        frequency: Annotated[RecurrenceFrequency, Field(description="The unit of the recurrence: daily, weekly, monthly, or yearly. Daily and weekly steps move by an exact number of days. Monthly and yearly steps are anchored on the day of the month of the start date, so a run never drifts after a short month. Any other value fails validation.")],
        repeat_every: Annotated[int, Field(description="How many frequency units separate consecutive dates. A value of one gives every unit, and larger values skip the units in between. It must be between 1 and 1,000. The default is one.", ge=1, le=PREBUILT_MAX_RECURRENCE_STEP)] = 1,
        occurrences: Annotated[int | None, Field(description="The most dates the recurrence may produce, counting the start date, from 1 to 1,000. It may be null when until_date is given instead. The series stops at whichever comes first of this count, until_date, and the last day of year 9999. Leaving both this and until_date null fails with an error naming this parameter.", ge=1, le=PREBUILT_MAX_RESULT_ITEMS)] = None,
        until_date: Annotated[date | None, Field(description="The last date the recurrence may reach, included when a step lands on it, written as an ISO calendar date in the YYYY-MM-DD form. It may be null when occurrences is given instead. A date before the start gives an empty list. A day that does not exist in its month fails validation.")] = None,
    ) -> PrebuiltToolOutput:
        """List the dates of a daily, weekly, monthly, or yearly recurrence that begins on a start date. Use it to lay out repeating events, billing cycles, or reminders. Monthly and yearly dates are anchored on the day of the month of the start and clamped in shorter months, so a run never drifts, and the series stops at the first of occurrences, until_date, or the last day of year 9999. At most 1,000 dates are listed while count covers the whole series, and leaving both occurrences and until_date null fails with an error naming occurrences."""
        # A recurrence needs a count or an end date to stop at.
        if occurrences is None and until_date is None:
            raise PrebuiltToolSupport.argument_error("occurrences", "neither occurrences nor until_date is given", "a number of occurrences, an until_date, or both")
        days_step, months_step = (repeat_every * unit for unit in _FREQUENCY_STEPS[frequency])
        last_allowed = until_date if until_date is not None else date.max

        # Count the steps that fit before the last allowed day without
        # listing them; a clamped month step can overshoot by one.
        total = SchedulingToolFunctions._steps_until(start_date, days_step, months_step, last_allowed)
        if total and SchedulingToolFunctions._recurrence_date(start_date, days_step, months_step, total - 1) > last_allowed:
            total -= 1
        if occurrences is not None:
            total = min(total, occurrences)

        # List the dates lazily up to the item cap.
        series = (SchedulingToolFunctions._recurrence_date(start_date, days_step, months_step, index).isoformat() for index in range(total))
        dates, truncated = PrebuiltToolSupport.cap_items(series)
        return {"dates": dates, "count": total, "truncated": truncated}

    @staticmethod
    def merge_time_intervals(
        starts: Annotated[list[datetime], Field(description="The start of each interval as an ISO 8601 date and time, paired by position with ends. A value without a UTC offset is read as UTC, and an offset is honored when present. The list must hold between 1 and 10,000 items. Each start must not come after its paired end.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        ends: Annotated[list[datetime], Field(description="The end of each interval as an ISO 8601 date and time, paired by position with starts. A value without a UTC offset is read as UTC. The list must have exactly as many items as starts, or the tool fails with an error naming this parameter. An end that comes before its paired start fails with an error naming this parameter and the index.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        output_offset: Annotated[str, Field(description=_OUTPUT_OFFSET_DESCRIPTION, pattern=_UTC_OFFSET_PATTERN, max_length=PREBUILT_MAX_UTC_OFFSET_CHARS)] = "+00:00",
    ) -> PrebuiltToolOutput:
        """Merge time intervals that overlap or touch into the fewest separate intervals, and total their length in minutes. Use it to combine calendar entries, work sessions, or outage windows before measuring them. Times without a UTC offset are read as UTC, and the merged intervals are sorted by start and written at output_offset. A length mismatch between starts and ends, or a start after its end, fails with an error naming ends."""
        # Pair each start with its end and read times without an offset
        # as UTC, refusing an interval that ends before it starts.
        spans = SchedulingToolFunctions._aware_spans(PrebuiltToolSupport.paired_values(starts, ends, "ends"), "ends")

        # Merge the spans that overlap or touch, in start order.
        merged = SchedulingToolFunctions._merge_spans(spans)

        # Write each merged span at the chosen offset and total them.
        zone = PrebuiltToolSupport.parse_utc_offset(output_offset)
        total = sum((end - start for start, end in merged), timedelta())
        return {"intervals": SchedulingToolFunctions._shown_spans(merged, zone), "total_minutes": total / _ONE_MINUTE}

    @staticmethod
    def find_common_free_slots(
        busy_starts: Annotated[list[datetime], Field(description="The start of each busy interval from every participant together, as ISO 8601 dates and times paired by position with busy_ends. A value without a UTC offset is read as UTC, and an offset is honored when present. The list may hold at most 10,000 items and may be empty. Busy intervals may overlap and need not be sorted.", max_length=PREBUILT_MAX_LIST_ITEMS)],
        busy_ends: Annotated[list[datetime], Field(description="The end of each busy interval, as ISO 8601 dates and times paired by position with busy_starts. A value without a UTC offset is read as UTC. The list must have exactly as many items as busy_starts, or the tool fails with an error naming this parameter. A busy end that comes before its paired start also fails with an error naming this parameter.", max_length=PREBUILT_MAX_LIST_ITEMS)],
        window_start: Annotated[datetime, Field(description="The beginning of the window in which free time is searched, as an ISO 8601 date and time. A value without a UTC offset is read as UTC. Free slots never start before this moment. It must come before window_end.")],
        window_end: Annotated[datetime, Field(description="The end of the window in which free time is searched, as an ISO 8601 date and time. A value without a UTC offset is read as UTC. Free slots never end after this moment. A window end at or before the window start fails with an error naming this parameter.")],
        minimum_minutes: Annotated[float, Field(description="The shortest free gap, in minutes, that counts as a slot. A gap exactly this long is kept. It must be greater than zero and at most 525,600, the minutes of a common year. The default is thirty minutes.", gt=0, le=PREBUILT_MAX_FREE_SLOT_MINUTES, allow_inf_nan=False)] = 30,
        output_offset: Annotated[str, Field(description=_OUTPUT_OFFSET_DESCRIPTION, pattern=_UTC_OFFSET_PATTERN, max_length=PREBUILT_MAX_UTC_OFFSET_CHARS)] = "+00:00",
    ) -> PrebuiltToolOutput:
        """Find the free time slots inside a window that are at least a minimum number of minutes long, given busy intervals from any number of participants. Use it to propose meeting times that suit everyone. Busy intervals are merged first, times without a UTC offset are read as UTC, and slots are written at output_offset in time order. At most 1,000 slots are listed while count covers all of them, a window end at or before its start fails with an error naming window_end, and a busy length mismatch or a busy start after its end fails with an error naming busy_ends."""
        # Read the window as aware times and refuse one with no length.
        opening, closing = PrebuiltToolSupport.as_utc(window_start), PrebuiltToolSupport.as_utc(window_end)
        if closing <= opening:
            raise PrebuiltToolSupport.argument_error("window_end", "the window ends at or before it starts", "a window end after the window start")

        # Merge the busy time of every participant into separate blocks.
        pairs = PrebuiltToolSupport.paired_values(busy_starts, busy_ends, "busy_ends")
        busy = SchedulingToolFunctions._merge_spans(SchedulingToolFunctions._aware_spans(pairs, "busy_ends"))

        # Keep the gaps inside the window that are long enough, compared
        # exactly in microseconds against the minimum's shortest text.
        gaps = SchedulingToolFunctions._free_gaps(busy, opening, closing, Fraction(repr(float(minimum_minutes))))

        # Write the slots at the chosen offset, listing up to the cap.
        zone = PrebuiltToolSupport.parse_utc_offset(output_offset)
        slots, truncated = PrebuiltToolSupport.cap_items(SchedulingToolFunctions._shown_spans(gaps, zone))
        return {"slots": slots, "count": len(gaps), "truncated": truncated}

    @staticmethod
    def sort_date_strings(
        dates: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_PHRASE_CHARS)]], Field(description="The date strings to sort, in any mix of the forms that parse_date_to_iso accepts. Each string may hold at most 200 characters, and the list may hold at most 10,000 strings. Strings that name the same date keep their input order. A string that cannot be read as a date fails with an error naming this parameter and the index.", max_length=PREBUILT_MAX_LIST_ITEMS)],
        day_first: Annotated[bool, Field(description=_DAY_FIRST_DESCRIPTION)] = False,
        descending: Annotated[bool, Field(description="Whether the latest date comes first. When false, the earliest date comes first. Equal dates keep their input order in both directions. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Sort date strings written in mixed formats by the dates they represent, and return each original string with its ISO date. Use it to put dates from different sources in order without converting them by hand first. Each string is read with the same rules as parse_date_to_iso, and strings naming the same date keep their input order. A string that cannot be read as a date fails with an error naming dates and the index."""
        # Read every string as a date, naming the first one that fails.
        readings: list[tuple[date, str]] = []
        for index, text in enumerate(dates):
            parsed = PrebuiltToolSupport.parse_date_text(text, day_first)
            if parsed is None:
                raise PrebuiltToolSupport.argument_error("dates", f"the string at index {index} is not a real date in an accepted form", "date strings in the forms that parse_date_to_iso accepts")
            readings.append((parsed[0], text))

        # Python's sort is stable in both directions, so equal dates
        # keep their input order.
        ordered = sorted(readings, key=lambda reading: reading[0], reverse=descending)
        return {"sorted": [{"original": text, "date": day.isoformat()} for day, text in ordered]}

    @staticmethod
    def _working_calendar(holidays: Sequence[date], weekend_days: Sequence[Weekday]) -> tuple[frozenset[int], list[int]]:
        """Return the weekend weekday numbers and the sorted distinct ordinals of holidays on working weekdays."""
        weekend = frozenset(_WEEKDAY_NUMBERS[day] for day in weekend_days)
        if len(weekend) == _DAYS_IN_WEEK:
            raise PrebuiltToolSupport.argument_error("weekend_days", "every day of the week is marked as weekend", "at most six distinct weekend days")
        return weekend, sorted({holiday.toordinal() for holiday in holidays if holiday.weekday() not in weekend})

    @staticmethod
    def _count_business_days(first: int, last: int, weekend: frozenset[int], holiday_ordinals: list[int]) -> int:
        """Count the working days from ordinal first to ordinal last, both included, with whole-week arithmetic."""
        # Whole weeks hold a fixed number of working days, the leftover
        # days are checked one by one, and holidays in range come off.
        full_weeks, extra_days = divmod(last - first + 1, _DAYS_IN_WEEK)
        working = full_weeks * (_DAYS_IN_WEEK - len(weekend))
        working += sum(1 for offset in range(extra_days) if (first + offset - 1) % _DAYS_IN_WEEK not in weekend)
        return working - (bisect.bisect_right(holiday_ordinals, last) - bisect.bisect_left(holiday_ordinals, first))

    @staticmethod
    def _find_business_ordinal(base: int, needed: int, step: int, weekend: frozenset[int], holiday_ordinals: list[int]) -> int:
        """Return the ordinal of the needed-th working day from base, base included, moving in the direction of step."""
        per_week = _DAYS_IN_WEEK - len(weekend)
        found = base
        while needed > 0:
            # Jump whole weeks, then find the remaining working weekdays
            # inside the next seven days.
            full_weeks = (needed - 1) // per_week
            week_start = base + step * _DAYS_IN_WEEK * full_weeks
            hits = [offset for offset in range(_DAYS_IN_WEEK) if (week_start + step * offset - 1) % _DAYS_IN_WEEK not in weekend]
            found = week_start + step * hits[needed - full_weeks * per_week - 1]
            # Holidays passed on the way were not working days, so the
            # search continues past them for that many more days.
            low, high = min(base, found), max(base, found)
            needed = bisect.bisect_right(holiday_ordinals, high) - bisect.bisect_left(holiday_ordinals, low)
            base = found + step
        return found

    @staticmethod
    def _steps_until(start: date, days_step: int, months_step: int, last_allowed: date) -> int:
        """Count recurrence dates up to last_allowed, which may be one too many when a clamped month step overshoots."""
        if last_allowed < start:
            return 0
        if months_step == 0:
            return (last_allowed - start).days // days_step + 1
        months = (last_allowed.year - start.year) * _MONTHS_IN_YEAR + last_allowed.month - start.month
        return months // months_step + 1

    @staticmethod
    def _recurrence_date(start: date, days_step: int, months_step: int, index: int) -> date:
        """Return the index-th recurrence date, anchoring month steps on the start's day of the month and clamping it."""
        if months_step == 0:
            return start + timedelta(days=index * days_step)
        year, month_index = divmod(start.year * _MONTHS_IN_YEAR + start.month - 1 + index * months_step, _MONTHS_IN_YEAR)
        return date(year, month_index + 1, min(start.day, calendar.monthrange(year, month_index + 1)[1]))

    @staticmethod
    def _aware_spans(pairs: Sequence[tuple[datetime, datetime]], parameter_name: str) -> list[tuple[datetime, datetime]]:
        """Read each start and end pair as aware datetimes, naive ones as UTC, refusing a pair that ends before it starts."""
        spans: list[tuple[datetime, datetime]] = []
        for index, (start, end) in enumerate(pairs):
            aware_start, aware_end = PrebuiltToolSupport.as_utc(start), PrebuiltToolSupport.as_utc(end)
            if aware_start > aware_end:
                raise PrebuiltToolSupport.argument_error(parameter_name, f"the interval at index {index} ends before it starts", "each end at or after its paired start")
            spans.append((aware_start, aware_end))
        return spans

    @staticmethod
    def _merge_spans(spans: Sequence[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
        """Merge spans that overlap or touch, returning separate spans sorted by start."""
        merged: list[tuple[datetime, datetime]] = []
        for start, end in sorted(spans, key=lambda span: span[0]):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged

    @staticmethod
    def _free_gaps(busy: Sequence[tuple[datetime, datetime]], opening: datetime, closing: datetime, minimum: Fraction) -> list[tuple[datetime, datetime]]:
        """Return the gaps between sorted busy spans inside the window that last at least minimum minutes."""
        gaps: list[tuple[datetime, datetime]] = []
        cursor = opening
        for start, end in busy:
            if cursor >= closing:
                break
            if start > cursor:
                gaps.append((cursor, min(start, closing)))
            cursor = max(cursor, end)
        if cursor < closing:
            gaps.append((cursor, closing))
        return [(start, end) for start, end in gaps if Fraction((end - start) // _ONE_MICROSECOND, _MICROSECONDS_PER_MINUTE) >= minimum]

    @staticmethod
    def _shown_spans(spans: Sequence[tuple[datetime, datetime]], zone: timezone) -> list[dict[str, object]]:
        """Write each span at the output offset with its length in minutes, refusing a time outside years 1 to 9999."""
        try:
            return [{"start": start.astimezone(zone).isoformat(), "end": end.astimezone(zone).isoformat(), "minutes": (end - start) / _ONE_MINUTE} for start, end in spans]
        except (OverflowError, ValueError) as exc:
            raise PrebuiltToolSupport.argument_error("output_offset", "a time written at this offset falls outside years 1 to 9999", "an offset that keeps every written time between years 1 and 9999") from exc

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.business_days_between,
            cls.add_business_days,
            cls.list_dates_in_range,
            cls.count_weekday_occurrences,
            cls.generate_recurring_dates,
            cls.merge_time_intervals,
            cls.find_common_free_slots,
            cls.sort_date_strings,
        )


__all__ = ["SchedulingToolFunctions"]
