"""FILE: vidbyte/tools/builtins/prebuilt/dates.py

PURPOSE: Defines DatesToolFunctions, the ten prebuilt calendar-date tools: the days between two dates, adding days, weeks, months, or years, the calendar difference in years, months, and days, the weekday and the ISO week of a date, the n-th weekday of a month, the next or previous weekday, English relative date phrases, reading a written date, and the fiscal quarter of a date.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the DATES category is chosen. Builds on PrebuiltToolSupport in _support.py for reading written dates and for the argument error, and on the Weekday, DateUnit, WeekdayOccurrence, and SearchDirection enums.
ARCHITECTURE NOTE: Every tool is a static method whose docstring's first paragraph is the model-facing description and whose parameters carry their own Field descriptions and caps, so FunctionTool builds the whole schema from the signature. Dates are plain datetime.date values of the proleptic Gregorian calendar, month and year steps go through one clamping helper, and every step that could leave years 1 to 9999 is caught and turned into an argument error naming the parameter the row gives.
FUNCTION INVENTORY: days_between_dates, add_to_date, years_months_days_between, day_of_week, iso_week_number, nth_weekday_of_month, next_weekday, resolve_relative_date_phrase, parse_date_to_iso, and fiscal_quarter are the tools; _shift_date moves a date by whole units with month clamping; _offset_phrase, _weekday_phrase, and _period_phrase read the three families of relative phrases; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new date tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.9, and its entry in tool_functions. A new relative phrase form adds a pattern and a branch in the matching phrase helper, and its wording in the phrase description and the error text.
WHAT NOT TO DO IN THIS FILE: 1. Do not read the clock: there is no today, now, or fromtimestamp, so relative phrases always use the reference date the caller passes. 2. Do not parse dates with strptime; written dates go through PrebuiltToolSupport.parse_date_text. 3. Do not let OverflowError or ValueError from date arithmetic escape; convert it with argument_error naming the row's parameter. 4. Do not add whole months as a fixed number of days; month and year steps keep the day of the month and clamp it.
KNOWN EDGE CASES: The first of January of year 1 is a Monday and the calendar ends on the thirty-first of December of year 9999, so a step past either end fails. A month step from the thirty-first lands on the last day of a shorter month and sets clamped. The ISO year of a date near the first of January can differ from its calendar year. A fifth weekday that a month lacks is a null date, not an error.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.9, section 9.2 items 11 and 13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_time.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import calendar
import re
from datetime import MAXYEAR, MINYEAR, date, timedelta
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_MAX_DATE_OFFSET,
    PREBUILT_MAX_PHRASE_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import (
    DateUnit,
    SearchDirection,
    Weekday,
    WeekdayOccurrence,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_DAYS_IN_WEEK = 7
_MONTHS_IN_YEAR = 12
_MONTHS_IN_QUARTER = 3
_WEEKDAYS = tuple(Weekday)
_WEEKDAY_NUMBERS = MappingProxyType({member: number for number, member in enumerate(Weekday)})
_UNIT_STEPS = MappingProxyType({DateUnit.DAYS: (1, 0), DateUnit.WEEKS: (_DAYS_IN_WEEK, 0), DateUnit.MONTHS: (0, 1), DateUnit.YEARS: (0, _MONTHS_IN_YEAR)})
_OCCURRENCE_WEEKS = MappingProxyType({WeekdayOccurrence.FIRST: 0, WeekdayOccurrence.SECOND: 1, WeekdayOccurrence.THIRD: 2, WeekdayOccurrence.FOURTH: 3, WeekdayOccurrence.FIFTH: 4})
_FIXED_PHRASES = MappingProxyType({"today": 0, "tomorrow": 1, "yesterday": -1, "day after tomorrow": 2, "day before yesterday": -2})
_PHRASE_UNITS = MappingProxyType({"day": DateUnit.DAYS, "week": DateUnit.WEEKS, "month": DateUnit.MONTHS, "year": DateUnit.YEARS})
_PERIOD_STEPS = MappingProxyType({"this": 0, "next": 1, "last": -1})
_AHEAD_PHRASE = re.compile(r"in (?P<count>[0-9]+|an?) (?P<unit>day|week|month|year)s?")
_FROM_NOW_OR_AGO_PHRASE = re.compile(r"(?P<count>[0-9]+|an?) (?P<unit>day|week|month|year)s? (?P<side>from now|ago)")
_WEEKDAY_PHRASE = re.compile(r"(?P<which>next|last|this) (?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday)")
_PERIOD_PHRASE = re.compile(r"(?P<which>next|last|this) (?P<period>week|month|year)")
_ACCEPTED_PHRASES = "one of today, tomorrow, yesterday, day after tomorrow, day before yesterday, in N units, N units from now, N units ago, or next, last, or this followed by a weekday name, week, month, or year, where N is digits or a or an and a unit is day, week, month, or year"
_ACCEPTED_DATE_FORMS = "a real date written as YYYY-MM-DD with dashes, slashes, or dots, as YYYYMMDD, as A/B/YYYY with slashes, dashes, or dots, or with an English month name and a four-digit year, optionally after a weekday name"
_OUT_OF_RANGE = "the resulting date falls outside years 1 to 9999"
_IN_RANGE = "input whose resulting date stays between years 1 and 9999"

_START_DATE_DESCRIPTION = "The date the calculation starts from, written as an ISO calendar date in the YYYY-MM-DD form. It must be a real day of the proleptic Gregorian calendar between year 1 and year 9999. A day that does not exist in its month fails validation. The date has no time of day and no time zone."
_END_DATE_DESCRIPTION = "The date the calculation ends at, written as an ISO calendar date in the YYYY-MM-DD form. It may come before the start date, which reverses the direction of the result. It must be a real day between year 1 and year 9999. A day that does not exist in its month fails validation."
_TARGET_DATE_DESCRIPTION = "The date to describe, written as an ISO calendar date in the YYYY-MM-DD form. It must be a real day of the proleptic Gregorian calendar between year 1 and year 9999. A day that does not exist in its month fails validation. The date has no time of day and no time zone."
_WEEKDAY_DESCRIPTION = "The day of the week to look for, written as a lowercase English weekday name. Every day from monday to sunday is accepted, and abbreviations are not. Weeks are the ordinary seven-day weeks of the Gregorian calendar. Any other value fails validation."


class DatesToolFunctions:
    """The dates category: calendar arithmetic, weekdays, weeks, relative phrases, written dates, and fiscal quarters."""

    @staticmethod
    def days_between_dates(
        start_date: Annotated[date, Field(description=_START_DATE_DESCRIPTION)],
        end_date: Annotated[date, Field(description=_END_DATE_DESCRIPTION)],
        include_end_date: Annotated[bool, Field(description="Whether the end date itself is counted as one more day. When true, the count grows by one away from zero, and equal dates count as one day. When false, the result is the plain difference between the dates. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Count the days from a start date to an end date, and split that count into whole weeks and leftover days. Use it for questions about how many days remain until an event or how long ago something happened, because counting days across months by hand is error-prone. The count is the end minus the start, negative when the end comes first, and include_end_date adds the end date itself to the count. Weeks truncate toward zero, the leftover days carry the same sign as the total, and the tool has no failure case beyond date validation."""
        # Take the plain difference, then count the end date itself when
        # asked, moving one day further from zero.
        days = (end_date - start_date).days
        if include_end_date:
            days += 1 if end_date >= start_date else -1

        # Split the absolute count into weeks and days, then restore the
        # sign so both parts point the same way as the total.
        weeks, remaining = divmod(abs(days), _DAYS_IN_WEEK)
        sign = -1 if days < 0 else 1
        return {"days": days, "weeks": sign * weeks, "remaining_days": sign * remaining}

    @staticmethod
    def add_to_date(
        start_date: Annotated[date, Field(description=_START_DATE_DESCRIPTION)],
        amount: Annotated[int, Field(description="How many units to add, which may be negative to move back in time. It must be between minus one million and one million. Zero returns the start date unchanged. A result outside years 1 to 9999 fails with an error naming this parameter.", ge=-PREBUILT_MAX_DATE_OFFSET, le=PREBUILT_MAX_DATE_OFFSET)],
        unit: Annotated[DateUnit, Field(description="The calendar unit of the amount: days, weeks, months, or years. Days and weeks move by an exact number of days. Months and years keep the day of the month and clamp it to the end of a shorter month. Any other value fails validation.")],
    ) -> PrebuiltToolOutput:
        """Add a number of days, weeks, months, or years to a date, or subtract them with a negative amount, and return the resulting date. Use it for due dates, renewals, and anniversaries, where month lengths and leap years make mental arithmetic unreliable. Month and year steps keep the day of the month and clamp it to the last day of a shorter target month, and the clamped flag reports when that happened. A result before year 1 or after year 9999 fails with an error naming amount."""
        moved, clamped = DatesToolFunctions._shift_date(start_date, amount, unit, "amount")
        return {"date": moved.isoformat(), "clamped": clamped}

    @staticmethod
    def years_months_days_between(
        start_date: Annotated[date, Field(description=_START_DATE_DESCRIPTION)],
        end_date: Annotated[date, Field(description=_END_DATE_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Give the calendar difference between two dates as whole years, months, and remaining days, the way ages and tenures are usually stated. Use it when an answer must read as a span of years and months rather than a raw day count. It finds the largest number of whole months that fits between the dates, clamping a late day of the month to shorter months, and counts the days left over. When the end comes before the start the dates are swapped and negative is true, so every part is zero or more. The tool has no failure case beyond date validation."""
        # Put the dates in order and remember whether they were swapped.
        negative = end_date < start_date
        first, last = (end_date, start_date) if negative else (start_date, end_date)

        # Try the month count of the two calendar months; when the
        # clamped day of that month overshoots, one month fewer fits.
        months = (last.year - first.year) * _MONTHS_IN_YEAR + last.month - first.month
        reached, _ = DatesToolFunctions._shift_date(first, months, DateUnit.MONTHS, "end_date")
        if reached > last:
            months -= 1
            reached, _ = DatesToolFunctions._shift_date(first, months, DateUnit.MONTHS, "end_date")

        # Split the months into years and count the leftover days.
        years, extra_months = divmod(months, _MONTHS_IN_YEAR)
        return {"years": years, "months": extra_months, "days": (last - reached).days, "negative": negative}

    @staticmethod
    def day_of_week(target_date: Annotated[date, Field(description=_TARGET_DATE_DESCRIPTION)]) -> PrebuiltToolOutput:
        """Tell which day of the week a date falls on, with its ISO weekday number and its day of the year. Use it whenever a weekday matters, because weekdays of dates that were not memorized are easy to get wrong. The weekday is a lowercase English name, the ISO weekday runs from one for Monday to seven for Sunday, and the day of the year starts at one on the first of January. Every valid date from year 1 to year 9999 works, and the tool has no failure case beyond date validation."""
        day_of_year = target_date.toordinal() - date(target_date.year, 1, 1).toordinal() + 1
        return {"weekday": _WEEKDAYS[target_date.weekday()].value, "iso_weekday": target_date.isoweekday(), "day_of_year": day_of_year}

    @staticmethod
    def iso_week_number(target_date: Annotated[date, Field(description=_TARGET_DATE_DESCRIPTION)]) -> PrebuiltToolOutput:
        """Give the ISO 8601 week-numbering year, week number, and weekday of a date, with a week label in the YYYY-Www form. Use it for week-based reports, sprint planning, or any system that numbers weeks the ISO way. ISO weeks start on Monday and week one holds the first Thursday of the year, so the ISO year can differ from the calendar year for dates near the first of January. The tool has no failure case beyond date validation."""
        iso_year, iso_week, iso_weekday = target_date.isocalendar()
        return {"iso_year": iso_year, "iso_week": iso_week, "iso_weekday": iso_weekday, "week_label": f"{iso_year:04d}-W{iso_week:02d}"}

    @staticmethod
    def nth_weekday_of_month(
        year: Annotated[int, Field(description="The calendar year of the month to search, as a whole number. It must be between 1 and 9999. Years follow the proleptic Gregorian calendar, including its leap year rule. Any year outside that range fails validation.", ge=MINYEAR, le=MAXYEAR)],
        month: Annotated[int, Field(description="The month to search, as a whole number from 1 for January to 12 for December. It is combined with year to pick one calendar month. The real length of that month, including a leap February, is used. Any other number fails validation.", ge=1, le=_MONTHS_IN_YEAR)],
        weekday: Annotated[Weekday, Field(description=_WEEKDAY_DESCRIPTION)],
        occurrence: Annotated[WeekdayOccurrence, Field(description="Which occurrence of the weekday to find inside the month. The values first through fifth count from the start of the month. The value last picks the final such weekday of the month. A fifth occurrence that the month lacks gives a null date.")],
    ) -> PrebuiltToolOutput:
        """Find the date of the first, second, third, fourth, fifth, or last occurrence of a weekday in a given month. Use it for holidays and recurring meetings that are defined by a weekday rule instead of a fixed day of the month. Occurrences count from the first day of the month, and last means the final such weekday before the month ends. A fifth occurrence that the month does not have gives a null date instead of an error, and the tool has no other failure case beyond validation."""
        # Find the length of the month and the weekday number sought.
        days_in_month = calendar.monthrange(year, month)[1]
        wanted = _WEEKDAY_NUMBERS[weekday]

        # The last occurrence steps back from the month's final day.
        if occurrence is WeekdayOccurrence.LAST:
            final_day = date(year, month, days_in_month)
            found = final_day - timedelta(days=(final_day.weekday() - wanted) % _DAYS_IN_WEEK)
            return {"date": found.isoformat()}

        # Other occurrences step forward from the first such weekday,
        # and a day past the month's end means the month lacks it.
        first_match = 1 + (wanted - date(year, month, 1).weekday()) % _DAYS_IN_WEEK
        day = first_match + _DAYS_IN_WEEK * _OCCURRENCE_WEEKS[occurrence]
        return {"date": date(year, month, day).isoformat() if day <= days_in_month else None}

    @staticmethod
    def next_weekday(
        start_date: Annotated[date, Field(description="The date the search starts from, written as an ISO calendar date in the YYYY-MM-DD form. It is skipped even when it falls on the weekday, unless include_start is true. It must be a real day between year 1 and year 9999. A result outside that range fails with an error naming this parameter.")],
        weekday: Annotated[Weekday, Field(description=_WEEKDAY_DESCRIPTION)],
        direction: Annotated[SearchDirection, Field(description="Whether to search forward to a later date or backward to an earlier one. The value next searches forward and the value previous searches backward. Backward results have a negative days_away. The default is next.")] = SearchDirection.NEXT,
        include_start: Annotated[bool, Field(description="Whether the start date itself may be the answer when it already falls on the weekday. When false, a matching start is skipped and the search moves a full week. When true, a matching start is returned with zero days away. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Find the next or previous date that falls on a given weekday, counting from a start date, with the number of days away. Use it for questions about the coming or the most recent occurrence of a weekday. The start date itself only counts when include_start is true, and days_away is negative when searching backward. A result before year 1 or after year 9999 fails with an error naming start_date."""
        # Measure the gap to the weekday in the chosen direction; a gap
        # of zero becomes a full week unless the start may count.
        wanted = _WEEKDAY_NUMBERS[weekday]
        if direction is SearchDirection.NEXT:
            days_away = (wanted - start_date.weekday()) % _DAYS_IN_WEEK
        else:
            days_away = -((start_date.weekday() - wanted) % _DAYS_IN_WEEK)
        if days_away == 0 and not include_start:
            days_away = _DAYS_IN_WEEK if direction is SearchDirection.NEXT else -_DAYS_IN_WEEK

        # Move the date, refusing a step past either calendar end.
        try:
            found = start_date + timedelta(days=days_away)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("start_date", _OUT_OF_RANGE, _IN_RANGE) from exc
        return {"date": found.isoformat(), "days_away": days_away}

    @staticmethod
    def resolve_relative_date_phrase(
        phrase: Annotated[str, Field(description="The English relative date phrase to resolve, matched without regard to case and with surrounding whitespace ignored. Accepted forms are today, tomorrow, yesterday, day after tomorrow, day before yesterday, in N units, N units from now, N units ago, and next, last, or this followed by a weekday name, week, month, or year. N is digits up to one million or the word a or an, and a unit is day, week, month, or year in singular or plural. Any other phrase fails with an error that lists the accepted forms.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        reference_date: Annotated[date, Field(description="The date the phrase is measured from, written as an ISO calendar date in the YYYY-MM-DD form. The tool never reads the current date from a clock, so pass the current date here when the phrase is about now. It must be a real day between year 1 and year 9999. A day that does not exist in its month fails validation.")],
        week_starts_on: Annotated[Weekday, Field(description="The weekday on which a week begins, used by this followed by a weekday name and by the this, next, and last week periods. It does not affect day, month, or year phrases. The value is a lowercase English weekday name. The default is monday.")] = Weekday.MONDAY,
    ) -> PrebuiltToolOutput:
        """Turn an English relative date phrase into a calendar date, measured from a reference date that the caller supplies. Use it to pin down phrases about today, tomorrow, a number of days, weeks, months, or years from now or ago, and the next, last, or this weekday, week, month, or year. Week, month, and year periods give their first day in date and their last day in end_date, and month and year steps clamp to shorter months. The phrase is case-insensitive, the reference date is never read from a clock, and any other phrase or a result outside years 1 to 9999 fails with an error naming phrase."""
        # Lowercase the phrase and collapse its whitespace so the forms
        # can be matched exactly.
        text = " ".join(phrase.split()).lower()

        # A fixed word or a counted offset moves the reference date by
        # whole units, clamping month and year steps.
        offset = DatesToolFunctions._offset_phrase(text)
        if offset is not None:
            moved, _ = DatesToolFunctions._shift_date(reference_date, offset[0], offset[1], "phrase")
            return {"date": moved.isoformat(), "end_date": None, "weekday": _WEEKDAYS[moved.weekday()].value}

        # A weekday phrase names one day near the reference date.
        day = DatesToolFunctions._weekday_phrase(text, reference_date, week_starts_on)
        if day is not None:
            return {"date": day.isoformat(), "end_date": None, "weekday": _WEEKDAYS[day.weekday()].value}

        # A period phrase names a whole week, month, or year; anything
        # left over is not an accepted form.
        period = DatesToolFunctions._period_phrase(text, reference_date, week_starts_on)
        if period is None:
            raise PrebuiltToolSupport.argument_error("phrase", "the phrase is not an accepted relative date form", _ACCEPTED_PHRASES)
        first, last = period
        return {"date": first.isoformat(), "end_date": last.isoformat(), "weekday": _WEEKDAYS[first.weekday()].value}

    @staticmethod
    def parse_date_to_iso(
        text: Annotated[str, Field(description="The written date to read, with surrounding whitespace ignored. It may begin with a weekday name, and an ISO date may be followed by a time that is ignored. Years must have four digits, and month names may be full English names, three-letter forms, or Sept in any case. Text in any other form fails with an error naming this parameter.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
        day_first: Annotated[bool, Field(description="Whether a numeric date whose first two parts could both be the month is read day first. When false, the first part is the month, as in the convention of the United States. A part greater than twelve is always the day, whatever this setting says. The default is false.")] = False,
    ) -> PrebuiltToolOutput:
        """Read a date written in a common numeric or English format and return it as an ISO date in the YYYY-MM-DD form. Use it to normalize dates from documents, forms, or messages before comparing or computing with them. It accepts ISO dates with dashes, slashes, or dots, compact eight-digit dates, numeric dates with the year last, and English month names with or without ordinal suffixes, after an optional leading weekday name. When both leading parts of a numeric date could be the month, day_first decides and ambiguous is true if the two readings differ. An impossible date or an unknown form fails with an error naming text."""
        parsed = PrebuiltToolSupport.parse_date_text(text, day_first)
        if parsed is None:
            raise PrebuiltToolSupport.argument_error("text", "the text is not a real date in an accepted form", _ACCEPTED_DATE_FORMS)
        found, ambiguous = parsed
        return {"date": found.isoformat(), "ambiguous": ambiguous}

    @staticmethod
    def fiscal_quarter(
        target_date: Annotated[date, Field(description=_TARGET_DATE_DESCRIPTION)],
        fiscal_year_start_month: Annotated[int, Field(description="The calendar month in which the fiscal year begins, from 1 for January to 12 for December. Quarters are three-month blocks counted from that month. The default of 1 gives calendar years and calendar quarters. Any other number fails validation.", ge=1, le=_MONTHS_IN_YEAR)] = 1,
    ) -> PrebuiltToolOutput:
        """Give the fiscal year and fiscal quarter a date falls in, with the first and last dates of that quarter, for a fiscal year that starts in any month. Use it for financial reporting questions where the business year does not match the calendar year. The fiscal year is named for the calendar year in which it ends, and a start month of 1 gives calendar years and calendar quarters. A quarter that would start before year 1 or end after year 9999 fails with an error naming target_date."""
        # Count the months since the fiscal year began to find the
        # quarter, and name the year after the calendar year it ends in.
        months_in = (target_date.month - fiscal_year_start_month) % _MONTHS_IN_YEAR
        quarter = months_in // _MONTHS_IN_QUARTER + 1
        opening_year = target_date.year - (1 if target_date.month < fiscal_year_start_month else 0)
        fiscal_year = opening_year + (0 if fiscal_year_start_month == 1 else 1)

        # Find the first and last months of the quarter as month counts,
        # refusing a quarter that leaves years 1 to 9999.
        first_month = opening_year * _MONTHS_IN_YEAR + fiscal_year_start_month - 1 + (quarter - 1) * _MONTHS_IN_QUARTER
        start_year, start_month = divmod(first_month, _MONTHS_IN_YEAR)
        end_year, end_month = divmod(first_month + _MONTHS_IN_QUARTER - 1, _MONTHS_IN_YEAR)
        if start_year < MINYEAR or end_year > MAXYEAR:
            raise PrebuiltToolSupport.argument_error("target_date", "the fiscal quarter of this date reaches outside years 1 to 9999", "a date whose fiscal quarter lies between years 1 and 9999")

        # Write the quarter's first day and its last day.
        last_day = calendar.monthrange(end_year, end_month + 1)[1]
        return {
            "fiscal_year": fiscal_year,
            "fiscal_quarter": quarter,
            "quarter_start": date(start_year, start_month + 1, 1).isoformat(),
            "quarter_end": date(end_year, end_month + 1, last_day).isoformat(),
        }

    @staticmethod
    def _shift_date(start: date, amount: int, unit: DateUnit, parameter_name: str) -> tuple[date, bool]:
        """Move a date by whole units, clamping month and year steps to the target month's last day, and say whether it clamped."""
        days_per_unit, months_per_unit = _UNIT_STEPS[unit]
        try:
            if months_per_unit == 0:
                return start + timedelta(days=amount * days_per_unit), False
            year, month_index = divmod(start.year * _MONTHS_IN_YEAR + start.month - 1 + amount * months_per_unit, _MONTHS_IN_YEAR)
            day = min(start.day, calendar.monthrange(year, month_index + 1)[1])
            return date(year, month_index + 1, day), day != start.day
        except (OverflowError, ValueError) as exc:
            raise PrebuiltToolSupport.argument_error(parameter_name, _OUT_OF_RANGE, _IN_RANGE) from exc

    @staticmethod
    def _offset_phrase(text: str) -> tuple[int, DateUnit] | None:
        """Read a fixed day word or a counted offset phrase as a signed amount and unit, or return None."""
        fixed = _FIXED_PHRASES.get(text)
        if fixed is not None:
            return fixed, DateUnit.DAYS
        found = _AHEAD_PHRASE.fullmatch(text) or _FROM_NOW_OR_AGO_PHRASE.fullmatch(text)
        if found is None:
            return None
        count = 1 if found["count"] in ("a", "an") else int(found["count"])
        if count > PREBUILT_MAX_DATE_OFFSET:
            raise PrebuiltToolSupport.argument_error("phrase", f"the number in the phrase is larger than {PREBUILT_MAX_DATE_OFFSET}", f"a number of at most {PREBUILT_MAX_DATE_OFFSET}")
        sign = -1 if found.groupdict().get("side") == "ago" else 1
        return sign * count, _PHRASE_UNITS[found["unit"]]

    @staticmethod
    def _weekday_phrase(text: str, reference: date, week_starts_on: Weekday) -> date | None:
        """Resolve next, last, or this followed by a weekday name, or return None for another phrase."""
        found = _WEEKDAY_PHRASE.fullmatch(text)
        if found is None:
            return None
        wanted, today, week_start = _WEEKDAY_NUMBERS[Weekday(found["weekday"])], reference.weekday(), _WEEKDAY_NUMBERS[week_starts_on]
        # Next and last skip the reference day itself; this stays inside
        # the reference's own week, which begins on week_starts_on.
        offsets = {
            "next": (wanted - today - 1) % _DAYS_IN_WEEK + 1,
            "last": -((today - wanted - 1) % _DAYS_IN_WEEK + 1),
            "this": (wanted - week_start) % _DAYS_IN_WEEK - (today - week_start) % _DAYS_IN_WEEK,
        }
        try:
            return reference + timedelta(days=offsets[found["which"]])
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("phrase", _OUT_OF_RANGE, _IN_RANGE) from exc

    @staticmethod
    def _period_phrase(text: str, reference: date, week_starts_on: Weekday) -> tuple[date, date] | None:
        """Resolve this, next, or last followed by week, month, or year to its first and last days, or return None."""
        found = _PERIOD_PHRASE.fullmatch(text)
        if found is None:
            return None
        step = _PERIOD_STEPS[found["which"]]
        try:
            match found["period"]:
                case "week":
                    back = (reference.weekday() - _WEEKDAY_NUMBERS[week_starts_on]) % _DAYS_IN_WEEK
                    first = reference + timedelta(days=step * _DAYS_IN_WEEK - back)
                    return first, first + timedelta(days=_DAYS_IN_WEEK - 1)
                case "month":
                    year, month_index = divmod(reference.year * _MONTHS_IN_YEAR + reference.month - 1 + step, _MONTHS_IN_YEAR)
                    last_day = calendar.monthrange(year, month_index + 1)[1]
                    return date(year, month_index + 1, 1), date(year, month_index + 1, last_day)
                case _:
                    year = reference.year + step
                    return date(year, 1, 1), date(year, _MONTHS_IN_YEAR, calendar.monthrange(year, _MONTHS_IN_YEAR)[1])
        except (OverflowError, ValueError) as exc:
            raise PrebuiltToolSupport.argument_error("phrase", _OUT_OF_RANGE, _IN_RANGE) from exc

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.days_between_dates,
            cls.add_to_date,
            cls.years_months_days_between,
            cls.day_of_week,
            cls.iso_week_number,
            cls.nth_weekday_of_month,
            cls.next_weekday,
            cls.resolve_relative_date_phrase,
            cls.parse_date_to_iso,
            cls.fiscal_quarter,
        )


__all__ = ["DatesToolFunctions"]
