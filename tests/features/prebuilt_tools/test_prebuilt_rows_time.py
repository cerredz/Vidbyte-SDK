"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_time.py

PURPOSE: Exact-output and error-behavior cases for every Appendix A row in A.9 dates, A.10 scheduling, and A.11 timestamps_durations (26 tools), called through FunctionTool.execute as a model would call them.
ROLE IN CODEBASE: One of the row files of the prebuilt tool feature pack; it proves AC-11 for its rows and EC-17, EC-18, EC-19, and EC-36, using the tool_runner fixture from tests/features/prebuilt_tools/conftest.py and the case builders in prebuilt_tool_harness.py.
ARCHITECTURE NOTE: Every expectation is a calendar fact computed by hand or by a different route (ordinal arithmetic, brute-force day loops in a scratch script), never by calling vidbyte code. Nothing reads the real clock: relative phrases always pass reference_date.
FUNCTION INVENTORY: test_time_rows_return_documented_output checks SUCCESS_CASES; test_time_rows_reject_bad_input checks FAILURE_CASES; test_list_dates_in_range_stops_at_the_item_cap and test_generate_recurring_dates_counts_past_the_item_cap check INV-17 truncation with full counts; consecutive_dates builds an expected run of dates from ordinals.
COMMON MODIFICATION PATTERNS: Add an ok(...) or bad(...) entry to the table of the row you extend; keep the full top-level key set of the row in every expected object.
WHAT NOT TO DO IN THIS FILE: 1. Do not compute an expectation by calling a prebuilt tool or its module; the value must come from the calendar or a separate route. 2. Do not use datetime.now, date.today, or fromtimestamp; every case fixes its own dates.
KNOWN EDGE CASES: Month and year steps clamp to the last day of the month (EC-18); a naive datetime is UTC (EC-19); negative Unix time works on every OS (EC-36); float seconds are rounded half-even from Decimal(repr(x)) (spec §9.2 item 17), so 2.0035 s is 2.004s, not the 2.003 a float route gives.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md Appendix A.9, A.10, A.11 and §9.2 items 11 and 17
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_time.py
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import FailureCase, SuccessCase, ToolRunner, bad, invalid, ok


def consecutive_dates(start: str, count: int, step_days: int = 1) -> list[str]:
    """ISO dates start, start + step, ... built from proleptic ordinals, a route independent of any tool."""
    first = dt.date.fromisoformat(start).toordinal()
    return [dt.date.fromordinal(first + index * step_days).isoformat() for index in range(count)]


def interval(start: str, end: str, minutes: float) -> dict[str, object]:
    """One merged interval or free slot as the A.10 rows return it."""
    return {"start": start, "end": end, "minutes": minutes}


DATES_SUCCESS = [
    # days_between_dates: 31 (Jan) + 29 (Feb 2024) = 60 days, 8 weeks and 4 days.
    ok("days_between_dates", {"start_date": "2024-01-01", "end_date": "2024-03-01"}, {"days": 60, "weeks": 8, "remaining_days": 4}, "leap-february"),
    ok("days_between_dates", {"start_date": "2024-01-01", "end_date": "2024-03-01", "include_end_date": True}, {"days": 61, "weeks": 8, "remaining_days": 5}, "include-end"),
    ok("days_between_dates", {"start_date": "2024-03-01", "end_date": "2024-01-01"}, {"days": -60, "weeks": -8, "remaining_days": -4}, "negative-truncates-toward-zero"),
    ok("days_between_dates", {"start_date": "2024-03-01", "end_date": "2024-01-01", "include_end_date": True}, {"days": -61, "weeks": -8, "remaining_days": -5}, "negative-include-end"),
    ok("days_between_dates", {"start_date": "2024-05-05", "end_date": "2024-05-05", "include_end_date": True}, {"days": 1, "weeks": 0, "remaining_days": 1}, "same-day-include-end"),
    # add_to_date: EC-18 clamping, and plain day and week steps that never clamp.
    ok("add_to_date", {"start_date": "2024-02-29", "amount": 1, "unit": "years"}, {"date": "2025-02-28", "clamped": True}, "leap-day-plus-year-clamps"),
    ok("add_to_date", {"start_date": "2025-01-31", "amount": 1, "unit": "months"}, {"date": "2025-02-28", "clamped": True}, "jan-31-plus-month-clamps"),
    ok("add_to_date", {"start_date": "2024-03-31", "amount": -1, "unit": "months"}, {"date": "2024-02-29", "clamped": True}, "minus-month-clamps-to-leap-day"),
    ok("add_to_date", {"start_date": "2024-02-29", "amount": 4, "unit": "years"}, {"date": "2028-02-29", "clamped": False}, "leap-to-leap-no-clamp"),
    ok("add_to_date", {"start_date": "2024-01-15", "amount": 2, "unit": "weeks"}, {"date": "2024-01-29", "clamped": False}, "weeks"),
    ok("add_to_date", {"start_date": "2024-12-25", "amount": 10, "unit": "days"}, {"date": "2025-01-04", "clamped": False}, "days-cross-year"),
    # years_months_days_between: largest m with add_months(start, m) <= end, then leftover days.
    ok("years_months_days_between", {"start_date": "2024-01-31", "end_date": "2024-03-01"}, {"years": 0, "months": 1, "days": 1, "negative": False}, "clamped-month"),
    ok("years_months_days_between", {"start_date": "2024-03-01", "end_date": "2024-01-31"}, {"years": 0, "months": 1, "days": 1, "negative": True}, "swapped"),
    ok("years_months_days_between", {"start_date": "2020-02-29", "end_date": "2024-02-28"}, {"years": 3, "months": 11, "days": 30, "negative": False}, "leap-start"),
    ok("years_months_days_between", {"start_date": "2000-01-01", "end_date": "2026-10-14"}, {"years": 26, "months": 9, "days": 13, "negative": False}, "decades"),
    ok("years_months_days_between", {"start_date": "2024-07-04", "end_date": "2024-07-04"}, {"years": 0, "months": 0, "days": 0, "negative": False}, "same-day"),
    # day_of_week: weekday value, ISO weekday 1..7, and day of the year.
    ok("day_of_week", {"target_date": "2024-02-29"}, {"weekday": "thursday", "iso_weekday": 4, "day_of_year": 60}, "leap-day"),
    ok("day_of_week", {"target_date": "2024-12-31"}, {"weekday": "tuesday", "iso_weekday": 2, "day_of_year": 366}, "last-day-leap-year"),
    ok("day_of_week", {"target_date": "2000-01-01"}, {"weekday": "saturday", "iso_weekday": 6, "day_of_year": 1}, "y2k"),
    ok("day_of_week", {"target_date": "0001-01-01"}, {"weekday": "monday", "iso_weekday": 1, "day_of_year": 1}, "proleptic-first-day"),
    # iso_week_number: the ISO year differs from the calendar year near January 1.
    ok("iso_week_number", {"target_date": "2021-01-01"}, {"iso_year": 2020, "iso_week": 53, "iso_weekday": 5, "week_label": "2020-W53"}, "belongs-to-previous-year"),
    ok("iso_week_number", {"target_date": "2024-12-30"}, {"iso_year": 2025, "iso_week": 1, "iso_weekday": 1, "week_label": "2025-W01"}, "belongs-to-next-year"),
    ok("iso_week_number", {"target_date": "2024-02-29"}, {"iso_year": 2024, "iso_week": 9, "iso_weekday": 4, "week_label": "2024-W09"}, "zero-padded-week"),
    # nth_weekday_of_month: fourth Thursday of November 2024, last Monday of May 2024, a fifth that exists and one that does not.
    ok("nth_weekday_of_month", {"year": 2024, "month": 11, "weekday": "thursday", "occurrence": "fourth"}, {"date": "2024-11-28"}, "fourth-thursday"),
    ok("nth_weekday_of_month", {"year": 2024, "month": 5, "weekday": "monday", "occurrence": "last"}, {"date": "2024-05-27"}, "last-monday"),
    ok("nth_weekday_of_month", {"year": 2024, "month": 2, "weekday": "thursday", "occurrence": "fifth"}, {"date": "2024-02-29"}, "fifth-exists"),
    ok("nth_weekday_of_month", {"year": 2023, "month": 2, "weekday": "thursday", "occurrence": "fifth"}, {"date": None}, "fifth-missing-is-null"),
    ok("nth_weekday_of_month", {"year": 2024, "month": 1, "weekday": "monday", "occurrence": "first"}, {"date": "2024-01-01"}, "first-on-day-one"),
    # next_weekday: 2024-01-01 is a Monday.
    ok("next_weekday", {"start_date": "2024-01-01", "weekday": "monday"}, {"date": "2024-01-08", "days_away": 7}, "same-weekday-skips-start"),
    ok("next_weekday", {"start_date": "2024-01-01", "weekday": "monday", "include_start": True}, {"date": "2024-01-01", "days_away": 0}, "include-start"),
    ok("next_weekday", {"start_date": "2024-01-01", "weekday": "friday"}, {"date": "2024-01-05", "days_away": 4}, "next-friday"),
    ok("next_weekday", {"start_date": "2024-01-01", "weekday": "friday", "direction": "previous"}, {"date": "2023-12-29", "days_away": -3}, "previous-is-negative"),
]

RELATIVE_SUCCESS = [
    # resolve_relative_date_phrase: the reference 2024-03-13 is a Wednesday; weekday is the weekday of `date`.
    ok("resolve_relative_date_phrase", {"phrase": "today", "reference_date": "2024-03-13"}, {"date": "2024-03-13", "end_date": None, "weekday": "wednesday"}, "today"),
    ok("resolve_relative_date_phrase", {"phrase": "Tomorrow", "reference_date": "2024-03-13"}, {"date": "2024-03-14", "end_date": None, "weekday": "thursday"}, "case-insensitive"),
    ok("resolve_relative_date_phrase", {"phrase": "  day before yesterday  ", "reference_date": "2024-03-13"}, {"date": "2024-03-11", "end_date": None, "weekday": "monday"}, "whitespace-ignored"),
    ok("resolve_relative_date_phrase", {"phrase": "in 3 weeks", "reference_date": "2024-03-13"}, {"date": "2024-04-03", "end_date": None, "weekday": "wednesday"}, "in-n-weeks"),
    ok("resolve_relative_date_phrase", {"phrase": "2 months ago", "reference_date": "2024-03-13"}, {"date": "2024-01-13", "end_date": None, "weekday": "saturday"}, "months-ago"),
    ok("resolve_relative_date_phrase", {"phrase": "a year from now", "reference_date": "2024-02-29"}, {"date": "2025-02-28", "end_date": None, "weekday": "friday"}, "a-year-clamps"),
    ok("resolve_relative_date_phrase", {"phrase": "next friday", "reference_date": "2024-03-13"}, {"date": "2024-03-15", "end_date": None, "weekday": "friday"}, "next-weekday"),
    ok("resolve_relative_date_phrase", {"phrase": "last wednesday", "reference_date": "2024-03-13"}, {"date": "2024-03-06", "end_date": None, "weekday": "wednesday"}, "last-weekday-strictly-before"),
    ok("resolve_relative_date_phrase", {"phrase": "next wednesday", "reference_date": "2024-03-13"}, {"date": "2024-03-20", "end_date": None, "weekday": "wednesday"}, "next-weekday-strictly-after"),
    ok("resolve_relative_date_phrase", {"phrase": "this sunday", "reference_date": "2024-03-13"}, {"date": "2024-03-17", "end_date": None, "weekday": "sunday"}, "this-sunday-monday-week"),
    ok("resolve_relative_date_phrase", {"phrase": "this sunday", "reference_date": "2024-03-13", "week_starts_on": "sunday"}, {"date": "2024-03-10", "end_date": None, "weekday": "sunday"}, "this-sunday-sunday-week"),
    ok("resolve_relative_date_phrase", {"phrase": "this week", "reference_date": "2024-03-13"}, {"date": "2024-03-11", "end_date": "2024-03-17", "weekday": "monday"}, "this-week"),
    ok("resolve_relative_date_phrase", {"phrase": "this week", "reference_date": "2024-03-13", "week_starts_on": "sunday"}, {"date": "2024-03-10", "end_date": "2024-03-16", "weekday": "sunday"}, "this-week-from-sunday"),
    ok("resolve_relative_date_phrase", {"phrase": "next month", "reference_date": "2024-03-13"}, {"date": "2024-04-01", "end_date": "2024-04-30", "weekday": "monday"}, "next-month"),
    ok("resolve_relative_date_phrase", {"phrase": "last month", "reference_date": "2024-03-13"}, {"date": "2024-02-01", "end_date": "2024-02-29", "weekday": "thursday"}, "last-month-leap"),
    ok("resolve_relative_date_phrase", {"phrase": "last year", "reference_date": "2024-03-13"}, {"date": "2023-01-01", "end_date": "2023-12-31", "weekday": "sunday"}, "last-year"),
    # parse_date_to_iso: EC-17 ambiguity, the over-12 rule, and the other accepted forms.
    ok("parse_date_to_iso", {"text": "03/04/2025"}, {"date": "2025-03-04", "ambiguous": True}, "ec17-month-first-default"),
    ok("parse_date_to_iso", {"text": "03/04/2025", "day_first": True}, {"date": "2025-04-03", "ambiguous": True}, "ec17-day-first"),
    ok("parse_date_to_iso", {"text": "13/04/2025"}, {"date": "2025-04-13", "ambiguous": False}, "part-over-12-is-day"),
    ok("parse_date_to_iso", {"text": "04/04/2025"}, {"date": "2025-04-04", "ambiguous": False}, "equal-parts-not-ambiguous"),
    ok("parse_date_to_iso", {"text": "25.12.2023"}, {"date": "2023-12-25", "ambiguous": False}, "dotted-day-first-by-value"),
    ok("parse_date_to_iso", {"text": "2024-2-9"}, {"date": "2024-02-09", "ambiguous": False}, "iso-one-digit-parts"),
    ok("parse_date_to_iso", {"text": "2024/02/29"}, {"date": "2024-02-29", "ambiguous": False}, "slashed-iso"),
    ok("parse_date_to_iso", {"text": "20240229"}, {"date": "2024-02-29", "ambiguous": False}, "compact"),
    ok("parse_date_to_iso", {"text": "Sept 5, 2024"}, {"date": "2024-09-05", "ambiguous": False}, "sept-abbreviation"),
    ok("parse_date_to_iso", {"text": "DEC 25 2023"}, {"date": "2023-12-25", "ambiguous": False}, "month-name-any-case"),
    ok("parse_date_to_iso", {"text": "March 1st, 2024"}, {"date": "2024-03-01", "ambiguous": False}, "ordinal-suffix"),
    ok("parse_date_to_iso", {"text": "Friday 1 March 2024"}, {"date": "2024-03-01", "ambiguous": False}, "leading-weekday"),
    ok("parse_date_to_iso", {"text": "3rd of July, 2024"}, {"date": "2024-07-03", "ambiguous": False}, "day-of-month"),
    ok("parse_date_to_iso", {"text": "2024-03-01T10:20:30"}, {"date": "2024-03-01", "ambiguous": False}, "time-ignored"),
    ok("parse_date_to_iso", {"text": "2024-03-01 10:20"}, {"date": "2024-03-01", "ambiguous": False}, "space-time-ignored"),
    # fiscal_quarter: the fiscal year is named for the calendar year in which it ends.
    ok("fiscal_quarter", {"target_date": "2024-02-29"}, {"fiscal_year": 2024, "fiscal_quarter": 1, "quarter_start": "2024-01-01", "quarter_end": "2024-03-31"}, "calendar-default"),
    ok("fiscal_quarter", {"target_date": "2024-10-01", "fiscal_year_start_month": 10}, {"fiscal_year": 2025, "fiscal_quarter": 1, "quarter_start": "2024-10-01", "quarter_end": "2024-12-31"}, "october-start"),
    ok("fiscal_quarter", {"target_date": "2024-02-29", "fiscal_year_start_month": 4}, {"fiscal_year": 2024, "fiscal_quarter": 4, "quarter_start": "2024-01-01", "quarter_end": "2024-03-31"}, "april-start-q4"),
    ok("fiscal_quarter", {"target_date": "2024-12-31", "fiscal_year_start_month": 2}, {"fiscal_year": 2025, "fiscal_quarter": 4, "quarter_start": "2024-11-01", "quarter_end": "2025-01-31"}, "quarter-crosses-year"),
]

SCHEDULING_SUCCESS = [
    # business_days_between: January 2024 has 23 weekdays (four full weeks plus Mon 29 to Wed 31).
    ok("business_days_between", {"start_date": "2024-01-01", "end_date": "2024-01-31"}, {"business_days": 23}, "january"),
    ok(
        "business_days_between",
        {"start_date": "2024-01-01", "end_date": "2024-01-31", "holidays": ["2024-01-01", "2024-01-15", "2024-01-15", "2024-01-06", "2024-02-01"]},
        {"business_days": 21},
        "holidays-dedupe-weekend-outside-ignored",
    ),
    ok("business_days_between", {"start_date": "2024-01-31", "end_date": "2024-01-01"}, {"business_days": -23}, "negative"),
    ok("business_days_between", {"start_date": "2024-01-06", "end_date": "2024-01-06"}, {"business_days": 0}, "single-weekend-day"),
    ok("business_days_between", {"start_date": "2024-01-08", "end_date": "2024-01-08"}, {"business_days": 1}, "single-workday-both-ends"),
    ok("business_days_between", {"start_date": "2024-01-01", "end_date": "2024-01-07", "weekend_days": ["friday", "saturday"]}, {"business_days": 5}, "custom-weekend"),
    ok("business_days_between", {"start_date": "2023-01-02", "end_date": "2023-12-29"}, {"business_days": 260}, "whole-year-arithmetic"),
    # add_business_days: the start date itself is not counted.
    ok("add_business_days", {"start_date": "2024-01-05", "business_days": 1}, {"date": "2024-01-08"}, "friday-plus-one"),
    ok("add_business_days", {"start_date": "2024-01-05", "business_days": 0}, {"date": "2024-01-05"}, "zero-on-business-day"),
    ok("add_business_days", {"start_date": "2024-01-06", "business_days": 0}, {"date": "2024-01-08"}, "zero-on-weekend-moves-forward"),
    ok("add_business_days", {"start_date": "2024-01-08", "business_days": -1}, {"date": "2024-01-05"}, "minus-one"),
    ok("add_business_days", {"start_date": "2024-01-06", "business_days": -1}, {"date": "2024-01-05"}, "minus-one-from-saturday"),
    ok("add_business_days", {"start_date": "2024-12-20", "business_days": 5, "holidays": ["2024-12-25", "2024-12-26"]}, {"date": "2024-12-31"}, "skips-holidays"),
    ok("add_business_days", {"start_date": "2024-01-01", "business_days": 10}, {"date": "2024-01-15"}, "two-weeks"),
    ok("add_business_days", {"start_date": "2024-01-04", "business_days": 1, "weekend_days": ["friday", "saturday"]}, {"date": "2024-01-07"}, "custom-weekend"),
    # list_dates_in_range: both ends included.
    ok(
        "list_dates_in_range",
        {"start_date": "2024-02-27", "end_date": "2024-03-02"},
        {"dates": ["2024-02-27", "2024-02-28", "2024-02-29", "2024-03-01", "2024-03-02"], "count": 5, "truncated": False},
        "across-leap-day",
    ),
    ok("list_dates_in_range", {"start_date": "2024-02-27", "end_date": "2024-03-02", "step_days": 2}, {"dates": ["2024-02-27", "2024-02-29", "2024-03-02"], "count": 3, "truncated": False}, "step"),
    ok(
        "list_dates_in_range",
        {"start_date": "2024-01-01", "end_date": "2024-01-14", "weekdays": ["friday", "monday"]},
        {"dates": ["2024-01-01", "2024-01-05", "2024-01-08", "2024-01-12"], "count": 4, "truncated": False},
        "weekday-filter",
    ),
    ok("list_dates_in_range", {"start_date": "2024-06-01", "end_date": "2024-06-01"}, {"dates": ["2024-06-01"], "count": 1, "truncated": False}, "single-day"),
    # count_weekday_occurrences: 2024 starts on a Monday and has 366 days, so it holds 53 Mondays and 52 Fridays.
    ok("count_weekday_occurrences", {"start_date": "2024-01-01", "end_date": "2024-12-31", "weekday": "monday"}, {"count": 53}, "mondays-2024"),
    ok("count_weekday_occurrences", {"start_date": "2024-01-01", "end_date": "2024-12-31", "weekday": "friday"}, {"count": 52}, "fridays-2024"),
    ok("count_weekday_occurrences", {"start_date": "2024-01-01", "end_date": "2024-01-01", "weekday": "sunday"}, {"count": 0}, "single-day-miss"),
    # 3,652,059 days from 0001-01-01 (a Monday) are 521,722 weeks and 5 days (Monday to Friday).
    ok("count_weekday_occurrences", {"start_date": "0001-01-01", "end_date": "9999-12-31", "weekday": "sunday"}, {"count": 521722}, "full-range-sundays"),
    ok("count_weekday_occurrences", {"start_date": "0001-01-01", "end_date": "9999-12-31", "weekday": "friday"}, {"count": 521723}, "full-range-fridays"),
    # generate_recurring_dates: monthly and yearly runs are anchored on the start day and clamped.
    ok(
        "generate_recurring_dates",
        {"start_date": "2024-01-31", "frequency": "monthly", "occurrences": 4},
        {"dates": ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"], "count": 4, "truncated": False},
        "monthly-anchor-does-not-drift",
    ),
    ok(
        "generate_recurring_dates",
        {"start_date": "2024-02-29", "frequency": "yearly", "occurrences": 3},
        {"dates": ["2024-02-29", "2025-02-28", "2026-02-28"], "count": 3, "truncated": False},
        "yearly-leap-anchor",
    ),
    ok(
        "generate_recurring_dates",
        {"start_date": "2024-01-01", "frequency": "daily", "repeat_every": 3, "until_date": "2024-01-10"},
        {"dates": ["2024-01-01", "2024-01-04", "2024-01-07", "2024-01-10"], "count": 4, "truncated": False},
        "until-inclusive",
    ),
    ok(
        "generate_recurring_dates",
        {"start_date": "2024-01-01", "frequency": "weekly", "occurrences": 10, "until_date": "2024-01-15"},
        {"dates": ["2024-01-01", "2024-01-08", "2024-01-15"], "count": 3, "truncated": False},
        "first-stop-wins",
    ),
    ok("generate_recurring_dates", {"start_date": "2024-01-10", "frequency": "weekly", "until_date": "2024-01-01"}, {"dates": [], "count": 0, "truncated": False}, "until-before-start"),
    ok(
        "generate_recurring_dates",
        {"start_date": "9999-10-31", "frequency": "monthly", "occurrences": 5},
        {"dates": ["9999-10-31", "9999-11-30", "9999-12-31"], "count": 3, "truncated": False},
        "stops-at-year-9999",
    ),
    ok(
        "generate_recurring_dates",
        {"start_date": "2024-01-31", "frequency": "monthly", "repeat_every": 2, "occurrences": 3},
        {"dates": ["2024-01-31", "2024-03-31", "2024-05-31"], "count": 3, "truncated": False},
        "every-second-month",
    ),
    # merge_time_intervals: overlapping and touching intervals merge; output is sorted and shown at output_offset.
    ok(
        "merge_time_intervals",
        {"starts": ["2024-01-01T09:00:00Z", "2024-01-01T09:30:00Z", "2024-01-01T11:00:00Z"], "ends": ["2024-01-01T10:00:00Z", "2024-01-01T10:30:00Z", "2024-01-01T11:15:00Z"]},
        {"intervals": [interval("2024-01-01T09:00:00+00:00", "2024-01-01T10:30:00+00:00", 90.0), interval("2024-01-01T11:00:00+00:00", "2024-01-01T11:15:00+00:00", 15.0)], "total_minutes": 105.0},
        "overlap",
    ),
    ok(
        "merge_time_intervals",
        {"starts": ["2024-01-01T10:00:00Z", "2024-01-01T09:00:00Z"], "ends": ["2024-01-01T11:00:00Z", "2024-01-01T10:00:00Z"], "output_offset": "Z"},
        {"intervals": [interval("2024-01-01T09:00:00+00:00", "2024-01-01T11:00:00+00:00", 120.0)], "total_minutes": 120.0},
        "touching-merge-z-shown-as-plus-zero",
    ),
    ok(
        "merge_time_intervals",
        {"starts": ["2024-01-01T12:00:00+02:00", "2024-01-01T09:00:00"], "ends": ["2024-01-01T13:00:00+02:00", "2024-01-01T09:30:00"], "output_offset": "-05:00"},
        {"intervals": [interval("2024-01-01T04:00:00-05:00", "2024-01-01T04:30:00-05:00", 30.0), interval("2024-01-01T05:00:00-05:00", "2024-01-01T06:00:00-05:00", 60.0)], "total_minutes": 90.0},
        "offsets-naive-utc-sorted",
    ),
    # find_common_free_slots: busy intervals merge first, then gaps of at least minimum_minutes are kept.
    ok(
        "find_common_free_slots",
        {
            "busy_starts": ["2024-01-01T09:00:00Z", "2024-01-01T09:30:00Z", "2024-01-01T13:00:00Z"],
            "busy_ends": ["2024-01-01T10:00:00Z", "2024-01-01T11:00:00Z", "2024-01-01T14:00:00Z"],
            "window_start": "2024-01-01T08:00:00Z",
            "window_end": "2024-01-01T17:00:00Z",
        },
        {
            "slots": [
                interval("2024-01-01T08:00:00+00:00", "2024-01-01T09:00:00+00:00", 60.0),
                interval("2024-01-01T11:00:00+00:00", "2024-01-01T13:00:00+00:00", 120.0),
                interval("2024-01-01T14:00:00+00:00", "2024-01-01T17:00:00+00:00", 180.0),
            ],
            "count": 3,
            "truncated": False,
        },
        "three-gaps",
    ),
    ok(
        "find_common_free_slots",
        {
            "busy_starts": ["2024-01-01T09:00:00Z", "2024-01-01T13:00:00Z"],
            "busy_ends": ["2024-01-01T11:00:00Z", "2024-01-01T14:00:00Z"],
            "window_start": "2024-01-01T08:00:00Z",
            "window_end": "2024-01-01T17:00:00Z",
            "minimum_minutes": 90,
        },
        {"slots": [interval("2024-01-01T11:00:00+00:00", "2024-01-01T13:00:00+00:00", 120.0), interval("2024-01-01T14:00:00+00:00", "2024-01-01T17:00:00+00:00", 180.0)], "count": 2, "truncated": False},
        "minimum-filters",
    ),
    ok(
        "find_common_free_slots",
        {"busy_starts": ["2024-01-01T07:00:00Z"], "busy_ends": ["2024-01-01T08:30:00Z"], "window_start": "2024-01-01T08:00:00Z", "window_end": "2024-01-01T09:00:00Z", "output_offset": "+05:30"},
        {"slots": [interval("2024-01-01T14:00:00+05:30", "2024-01-01T14:30:00+05:30", 30.0)], "count": 1, "truncated": False},
        "exact-minimum-kept-shown-at-offset",
    ),
    ok(
        "find_common_free_slots",
        {"busy_starts": [], "busy_ends": [], "window_start": "2024-01-01T08:00:00", "window_end": "2024-01-01T17:00:00"},
        {"slots": [interval("2024-01-01T08:00:00+00:00", "2024-01-01T17:00:00+00:00", 540.0)], "count": 1, "truncated": False},
        "no-busy-naive-window",
    ),
    # sort_date_strings: mixed formats parse with the parse_date_to_iso rules; ties keep input order.
    ok(
        "sort_date_strings",
        {"dates": ["March 5, 2024", "2024-01-15", "03/04/2024", "20231231"]},
        {"sorted": [{"original": "20231231", "date": "2023-12-31"}, {"original": "2024-01-15", "date": "2024-01-15"}, {"original": "03/04/2024", "date": "2024-03-04"}, {"original": "March 5, 2024", "date": "2024-03-05"}]},
        "mixed-formats",
    ),
    ok(
        "sort_date_strings",
        {"dates": ["March 5, 2024", "2024-01-15", "03/04/2024", "20231231"], "day_first": True},
        {"sorted": [{"original": "20231231", "date": "2023-12-31"}, {"original": "2024-01-15", "date": "2024-01-15"}, {"original": "March 5, 2024", "date": "2024-03-05"}, {"original": "03/04/2024", "date": "2024-04-03"}]},
        "day-first",
    ),
    ok(
        "sort_date_strings",
        {"dates": ["2024-01-01", "1 Jan 2024", "2023-06-01"], "descending": True},
        {"sorted": [{"original": "2024-01-01", "date": "2024-01-01"}, {"original": "1 Jan 2024", "date": "2024-01-01"}, {"original": "2023-06-01", "date": "2023-06-01"}]},
        "descending-stable",
    ),
    ok(
        "sort_date_strings",
        {"dates": ["1 Jan 2024", "2023-06-01", "2024-01-01"]},
        {"sorted": [{"original": "2023-06-01", "date": "2023-06-01"}, {"original": "1 Jan 2024", "date": "2024-01-01"}, {"original": "2024-01-01", "date": "2024-01-01"}]},
        "ascending-stable",
    ),
    ok("sort_date_strings", {"dates": []}, {"sorted": []}, "empty"),
]

TIMESTAMP_SUCCESS = [
    # unix_timestamp_to_datetime: epoch plus exact microseconds, half-even, so negative values work everywhere (EC-36).
    ok("unix_timestamp_to_datetime", {"timestamp": 0}, {"datetime": "1970-01-01T00:00:00+00:00", "date": "1970-01-01", "time": "00:00:00", "weekday": "thursday"}, "epoch"),
    ok("unix_timestamp_to_datetime", {"timestamp": -86400}, {"datetime": "1969-12-31T00:00:00+00:00", "date": "1969-12-31", "time": "00:00:00", "weekday": "wednesday"}, "ec36-negative"),
    ok("unix_timestamp_to_datetime", {"timestamp": 1700000000}, {"datetime": "2023-11-14T22:13:20+00:00", "date": "2023-11-14", "time": "22:13:20", "weekday": "tuesday"}, "seconds"),
    ok(
        "unix_timestamp_to_datetime",
        {"timestamp": 1700000000123, "unit": "milliseconds"},
        {"datetime": "2023-11-14T22:13:20.123000+00:00", "date": "2023-11-14", "time": "22:13:20.123000", "weekday": "tuesday"},
        "milliseconds",
    ),
    ok("unix_timestamp_to_datetime", {"timestamp": 0, "utc_offset": "+05:30"}, {"datetime": "1970-01-01T05:30:00+05:30", "date": "1970-01-01", "time": "05:30:00", "weekday": "thursday"}, "positive-offset"),
    ok("unix_timestamp_to_datetime", {"timestamp": 0, "utc_offset": "-05:00"}, {"datetime": "1969-12-31T19:00:00-05:00", "date": "1969-12-31", "time": "19:00:00", "weekday": "wednesday"}, "negative-offset-previous-day"),
    ok("unix_timestamp_to_datetime", {"timestamp": -0.5}, {"datetime": "1969-12-31T23:59:59.500000+00:00", "date": "1969-12-31", "time": "23:59:59.500000", "weekday": "wednesday"}, "negative-fraction"),
    ok("unix_timestamp_to_datetime", {"timestamp": 0.0000025}, {"datetime": "1970-01-01T00:00:00.000002+00:00", "date": "1970-01-01", "time": "00:00:00.000002", "weekday": "thursday"}, "half-even-tie-down"),
    ok("unix_timestamp_to_datetime", {"timestamp": 0.0000015}, {"datetime": "1970-01-01T00:00:00.000002+00:00", "date": "1970-01-01", "time": "00:00:00.000002", "weekday": "thursday"}, "half-even-tie-up"),
    ok("unix_timestamp_to_datetime", {"timestamp": 3500, "unit": "nanoseconds"}, {"datetime": "1970-01-01T00:00:00.000004+00:00", "date": "1970-01-01", "time": "00:00:00.000004", "weekday": "thursday"}, "nanoseconds-tie"),
    ok("unix_timestamp_to_datetime", {"timestamp": 2500, "unit": "nanoseconds"}, {"datetime": "1970-01-01T00:00:00.000002+00:00", "date": "1970-01-01", "time": "00:00:00.000002", "weekday": "thursday"}, "nanoseconds-tie-even"),
    ok("unix_timestamp_to_datetime", {"timestamp": 86400000000, "unit": "microseconds"}, {"datetime": "1970-01-02T00:00:00+00:00", "date": "1970-01-02", "time": "00:00:00", "weekday": "friday"}, "microseconds"),
    # datetime_to_unix_timestamp: floor to a whole unit; naive is UTC (EC-19); integer text.
    ok("datetime_to_unix_timestamp", {"moment": "1970-01-01T00:00:00Z"}, {"timestamp": "0"}, "epoch-zero-text"),
    ok("datetime_to_unix_timestamp", {"moment": "2023-11-14T22:13:20Z"}, {"timestamp": "1700000000"}, "seconds"),
    ok("datetime_to_unix_timestamp", {"moment": "2023-11-14T22:13:20"}, {"timestamp": "1700000000"}, "ec19-naive-is-utc"),
    ok("datetime_to_unix_timestamp", {"moment": "2023-11-15T03:43:20+05:30"}, {"timestamp": "1700000000"}, "offset-honored"),
    ok("datetime_to_unix_timestamp", {"moment": "2023-11-14T22:13:20.123456Z", "unit": "nanoseconds"}, {"timestamp": "1700000000123456000"}, "nanoseconds-past-2-53"),
    ok("datetime_to_unix_timestamp", {"moment": "1969-12-31T23:59:59.999Z"}, {"timestamp": "-1"}, "floor-negative-seconds"),
    ok("datetime_to_unix_timestamp", {"moment": "1969-12-31T23:59:59.999Z", "unit": "milliseconds"}, {"timestamp": "-1"}, "milliseconds-negative"),
    ok("datetime_to_unix_timestamp", {"moment": "2023-11-14T22:13:20.123999Z", "unit": "milliseconds"}, {"timestamp": "1700000000123"}, "milliseconds-floor"),
    ok("datetime_to_unix_timestamp", {"moment": "0001-01-01T00:00:00Z"}, {"timestamp": "-62135596800"}, "year-one"),
    # convert_utc_offset: day_shift is the output local date minus the input local date.
    ok("convert_utc_offset", {"moment": "2024-01-01T00:30:00Z", "to_offset": "-05:00"}, {"datetime": "2023-12-31T19:30:00-05:00", "date": "2023-12-31", "time": "19:30:00", "day_shift": -1}, "back-a-day"),
    ok("convert_utc_offset", {"moment": "2024-01-01T23:30:00-02:00", "to_offset": "+09:00"}, {"datetime": "2024-01-02T10:30:00+09:00", "date": "2024-01-02", "time": "10:30:00", "day_shift": 1}, "forward-a-day"),
    ok("convert_utc_offset", {"moment": "2024-06-01T12:00:00", "to_offset": "Z"}, {"datetime": "2024-06-01T12:00:00+00:00", "date": "2024-06-01", "time": "12:00:00", "day_shift": 0}, "naive-to-z"),
    ok("convert_utc_offset", {"moment": "2024-01-01T12:00:00+00:00", "to_offset": "+23:59"}, {"datetime": "2024-01-02T11:59:00+23:59", "date": "2024-01-02", "time": "11:59:00", "day_shift": 1}, "largest-offset"),
    # duration_between_datetimes: total is signed; the parts break down the absolute difference.
    ok(
        "duration_between_datetimes",
        {"start": "2024-01-01T00:00:00Z", "end": "2024-01-02T01:02:03.5Z"},
        {"total_seconds": 90123.5, "days": 1, "hours": 1, "minutes": 2, "seconds": 3.5, "negative": False},
        "parts",
    ),
    ok(
        "duration_between_datetimes",
        {"start": "2024-01-02T01:02:03.5Z", "end": "2024-01-01T00:00:00Z"},
        {"total_seconds": -90123.5, "days": 1, "hours": 1, "minutes": 2, "seconds": 3.5, "negative": True},
        "negative",
    ),
    ok(
        "duration_between_datetimes",
        {"start": "2024-03-10T01:00:00-05:00", "end": "2024-03-10T03:00:00-04:00"},
        {"total_seconds": 3600.0, "days": 0, "hours": 1, "minutes": 0, "seconds": 0.0, "negative": False},
        "offsets-honored",
    ),
    ok("duration_between_datetimes", {"start": "2024-01-01T00:00:00", "end": "2024-01-01T00:00:00Z"}, {"total_seconds": 0.0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0.0, "negative": False}, "naive-equals-utc"),
    # add_duration_to_datetime: elapsed time that keeps the input offset.
    ok("add_duration_to_datetime", {"moment": "2024-02-28T23:00:00+05:30", "hours": 2}, {"datetime": "2024-02-29T01:00:00+05:30", "date": "2024-02-29", "time": "01:00:00"}, "keeps-offset"),
    ok("add_duration_to_datetime", {"moment": "2024-03-01T00:00:00Z", "days": -1, "seconds": 0.25}, {"datetime": "2024-02-29T00:00:00.250000+00:00", "date": "2024-02-29", "time": "00:00:00.250000"}, "negative-days-fraction"),
    ok("add_duration_to_datetime", {"moment": "2024-01-01T00:00:00", "minutes": 90}, {"datetime": "2024-01-01T01:30:00+00:00", "date": "2024-01-01", "time": "01:30:00"}, "naive-is-utc"),
    ok("add_duration_to_datetime", {"moment": "2024-01-01T00:00:00Z", "days": 1, "hours": -1, "minutes": 30, "seconds": -30}, {"datetime": "2024-01-01T23:29:30+00:00", "date": "2024-01-01", "time": "23:29:30"}, "mixed-signs"),
    ok("add_duration_to_datetime", {"moment": "2024-01-01T00:00:00Z"}, {"datetime": "2024-01-01T00:00:00+00:00", "date": "2024-01-01", "time": "00:00:00"}, "defaults-are-zero"),
]

DURATION_SUCCESS = [
    # format_duration: 93,784 s is 1 day, 2 hours, 3 minutes, 4 seconds.
    ok("format_duration", {"seconds": 93784}, {"text": "1d 2h 3m 4s"}, "compact-default"),
    ok("format_duration", {"seconds": 93784, "style": "long"}, {"text": "1 day, 2 hours, 3 minutes, 4 seconds"}, "long"),
    ok("format_duration", {"seconds": 90061, "style": "long"}, {"text": "1 day, 1 hour, 1 minute, 1 second"}, "long-singular"),
    ok("format_duration", {"seconds": 93784, "style": "clock"}, {"text": "26:03:04"}, "clock-hours-past-24"),
    ok("format_duration", {"seconds": 93784, "style": "iso8601"}, {"text": "P1DT2H3M4S"}, "iso8601"),
    ok("format_duration", {"seconds": 3604}, {"text": "1h 4s"}, "compact-skips-zero-parts"),
    ok("format_duration", {"seconds": 172800, "style": "iso8601"}, {"text": "P2D"}, "iso8601-days-only"),
    ok("format_duration", {"seconds": 3600, "style": "iso8601"}, {"text": "PT1H"}, "iso8601-hours-only"),
    ok("format_duration", {"seconds": 1209600, "style": "iso8601"}, {"text": "P14D"}, "iso8601-days-at-most"),
    ok("format_duration", {"seconds": 3661.25, "style": "clock"}, {"text": "1:01:01.25"}, "clock-fraction-no-trailing-zero"),
    ok("format_duration", {"seconds": 90.5}, {"text": "1m 30.5s"}, "compact-fraction"),
    ok("format_duration", {"seconds": -90}, {"text": "-1m 30s"}, "negative-prefix"),
    ok("format_duration", {"seconds": -90, "style": "clock"}, {"text": "-0:01:30"}, "negative-clock"),
    # §9.2 item 17: Decimal(repr(x)) rounded half-even to whole milliseconds before splitting.
    ok("format_duration", {"seconds": 0.0125}, {"text": "0.012s"}, "item17-tie-to-even-down"),
    ok("format_duration", {"seconds": 0.0375}, {"text": "0.038s"}, "item17-tie-to-even-up"),
    ok("format_duration", {"seconds": 2.0035}, {"text": "2.004s"}, "item17-decimal-not-float-route"),
    ok("format_duration", {"seconds": 59.9996}, {"text": "1m"}, "item17-rounds-before-split"),
    ok("format_duration", {"seconds": 0.0125, "style": "iso8601"}, {"text": "PT0.012S"}, "iso8601-fraction"),
    ok("format_duration", {"seconds": -0.0004}, {"text": "0s"}, "negative-rounds-to-zero-no-sign"),
    ok("format_duration", {"seconds": 0, "style": "long"}, {"text": "0 seconds"}, "zero-long"),
    # Spec r4: long leaves out zero parts too.
    ok("format_duration", {"seconds": 3600, "style": "long"}, {"text": "1 hour"}, "long-skips-zero-parts"),
    ok("format_duration", {"seconds": 86401, "style": "long"}, {"text": "1 day, 1 second"}, "long-skips-inner-zero-parts"),
    ok("format_duration", {"seconds": 0, "style": "clock"}, {"text": "0:00:00"}, "zero-clock"),
    ok("format_duration", {"seconds": 0, "style": "iso8601"}, {"text": "PT0S"}, "zero-iso8601"),
    # parse_duration_text: exact Decimal sum, and iso8601 is format_duration's iso8601 text of that sum.
    ok("parse_duration_text", {"text": "1h 30m"}, {"total_seconds": 5400.0, "iso8601": "PT1H30M"}, "unit-phrase"),
    ok("parse_duration_text", {"text": "PT1H30M"}, {"total_seconds": 5400.0, "iso8601": "PT1H30M"}, "iso-input"),
    ok("parse_duration_text", {"text": "P1W"}, {"total_seconds": 604800.0, "iso8601": "P7D"}, "iso-week-becomes-days"),
    ok("parse_duration_text", {"text": "P1DT0.5S"}, {"total_seconds": 86400.5, "iso8601": "P1DT0.5S"}, "iso-fraction"),
    ok("parse_duration_text", {"text": "1:02:03.5"}, {"total_seconds": 3723.5, "iso8601": "PT1H2M3.5S"}, "clock-with-fraction"),
    ok("parse_duration_text", {"text": "2:30"}, {"total_seconds": 9000.0, "iso8601": "PT2H30M"}, "clock-h-mm"),
    ok("parse_duration_text", {"text": "2 weeks, 3 days and 4 hours"}, {"total_seconds": 1483200.0, "iso8601": "P17DT4H"}, "commas-and"),
    ok("parse_duration_text", {"text": "250ms"}, {"total_seconds": 0.25, "iso8601": "PT0.25S"}, "milliseconds"),
    ok("parse_duration_text", {"text": "90 secs"}, {"total_seconds": 90.0, "iso8601": "PT1M30S"}, "plural-secs"),
    ok("parse_duration_text", {"text": "1.5 hrs"}, {"total_seconds": 5400.0, "iso8601": "PT1H30M"}, "fractional-hours"),
    # minutes_between_times: wraps past midnight.
    ok("minutes_between_times", {"start_time": "09:00", "end_time": "17:30"}, {"minutes": 510.0, "wrapped": False}, "workday"),
    ok("minutes_between_times", {"start_time": "22:00", "end_time": "02:15"}, {"minutes": 255.0, "wrapped": True}, "wraps-midnight"),
    ok("minutes_between_times", {"start_time": "12:00", "end_time": "12:00"}, {"minutes": 0.0, "wrapped": False}, "equal-is-zero"),
    ok("minutes_between_times", {"start_time": "00:00:30", "end_time": "00:01:00"}, {"minutes": 0.5, "wrapped": False}, "seconds"),
]

SUCCESS_CASES = DATES_SUCCESS + RELATIVE_SUCCESS + SCHEDULING_SUCCESS + TIMESTAMP_SUCCESS + DURATION_SUCCESS

FAILURE_CASES = [
    # A.9 dates
    invalid("days_between_dates", {"start_date": "2023-02-29", "end_date": "2024-01-01"}, "start_date", "impossible-date"),
    bad("add_to_date", {"start_date": "9999-12-31", "amount": 1, "unit": "days"}, "amount", "past-year-9999"),
    bad("add_to_date", {"start_date": "0001-01-01", "amount": -1, "unit": "months"}, "amount", "before-year-1"),
    invalid("add_to_date", {"start_date": "2024-01-01", "amount": 1000001, "unit": "days"}, "amount", "over-offset-bound"),
    invalid("add_to_date", {"start_date": "2024-01-01", "amount": 1, "unit": "fortnights"}, "unit", "unknown-unit"),
    invalid("nth_weekday_of_month", {"year": 2024, "month": 13, "weekday": "monday", "occurrence": "first"}, "month", "month-13"),
    invalid("nth_weekday_of_month", {"year": 0, "month": 1, "weekday": "monday", "occurrence": "first"}, "year", "year-zero"),
    bad("next_weekday", {"start_date": "9999-12-31", "weekday": "monday"}, "start_date", "past-year-9999"),
    bad("next_weekday", {"start_date": "0001-01-01", "weekday": "sunday", "direction": "previous"}, "start_date", "before-year-1"),
    bad("resolve_relative_date_phrase", {"phrase": "fortnight hence", "reference_date": "2024-03-13"}, "phrase", "unknown-phrase"),
    bad("resolve_relative_date_phrase", {"phrase": "in 10000 years", "reference_date": "2024-03-13"}, "phrase", "out-of-range"),
    invalid("resolve_relative_date_phrase", {"phrase": "", "reference_date": "2024-03-13"}, "phrase", "empty"),
    bad("parse_date_to_iso", {"text": "13/14/2025"}, "text", "both-parts-over-12"),
    bad("parse_date_to_iso", {"text": "2023-02-29"}, "text", "impossible-date"),
    bad("parse_date_to_iso", {"text": "02/30/2024"}, "text", "impossible-slashed"),
    bad("parse_date_to_iso", {"text": "yesterday"}, "text", "unknown-form"),
    invalid("fiscal_quarter", {"target_date": "2024-01-01", "fiscal_year_start_month": 0}, "fiscal_year_start_month", "month-zero"),
    # Spec r4 names target_date when the quarter would leave years 1 to 9999 (November to January quarters with a February start).
    bad("fiscal_quarter", {"target_date": "9999-12-31", "fiscal_year_start_month": 2}, "target_date", "quarter-ends-after-9999"),
    bad("fiscal_quarter", {"target_date": "0001-01-01", "fiscal_year_start_month": 2}, "target_date", "quarter-starts-before-year-1"),
    # A.10 scheduling
    invalid("business_days_between", {"start_date": "2024-01-01", "end_date": "2024-01-31", "weekend_days": ["monday"] * 8}, "weekend_days", "eight-weekend-days"),
    bad(
        "business_days_between",
        {"start_date": "2024-01-01", "end_date": "2024-01-31", "weekend_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]},
        "weekend_days",
        "all-days-weekend",
    ),
    bad(
        "add_business_days",
        {"start_date": "2024-01-01", "business_days": 1, "weekend_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]},
        "weekend_days",
        "all-days-weekend",
    ),
    bad("add_business_days", {"start_date": "9999-12-31", "business_days": 1}, "business_days", "past-year-9999"),
    invalid("add_business_days", {"start_date": "2024-01-01", "business_days": 100001}, "business_days", "over-bound"),
    bad("list_dates_in_range", {"start_date": "2024-01-02", "end_date": "2024-01-01"}, "end_date", "end-before-start"),
    bad("list_dates_in_range", {"start_date": "2000-01-01", "end_date": "2200-01-01"}, "end_date", "span-over-cap"),
    invalid("list_dates_in_range", {"start_date": "2024-01-01", "end_date": "2024-01-02", "step_days": 0}, "step_days", "zero-step"),
    bad("count_weekday_occurrences", {"start_date": "2024-01-02", "end_date": "2024-01-01", "weekday": "monday"}, "end_date", "end-before-start"),
    bad("generate_recurring_dates", {"start_date": "2024-01-01", "frequency": "daily"}, "occurrences", "no-stop"),
    invalid("generate_recurring_dates", {"start_date": "2024-01-01", "frequency": "daily", "occurrences": 1001}, "occurrences", "over-item-cap"),
    invalid("generate_recurring_dates", {"start_date": "2024-01-01", "frequency": "daily", "repeat_every": 0, "occurrences": 2}, "repeat_every", "zero-step"),
    bad("merge_time_intervals", {"starts": ["2024-01-01T09:00:00Z", "2024-01-01T10:00:00Z"], "ends": ["2024-01-01T09:30:00Z"]}, "ends", "length-mismatch"),
    bad("merge_time_intervals", {"starts": ["2024-01-01T09:00:00Z"], "ends": ["2024-01-01T08:00:00Z"]}, "ends", "start-after-end"),
    invalid("merge_time_intervals", {"starts": [], "ends": ["2024-01-01T10:00:00Z"]}, "starts", "empty-starts"),
    invalid("merge_time_intervals", {"starts": ["2024-01-01T09:00:00Z"], "ends": ["2024-01-01T10:00:00Z"], "output_offset": "+24:00"}, "output_offset", "offset-out-of-pattern"),
    bad(
        "find_common_free_slots",
        {"busy_starts": [], "busy_ends": [], "window_start": "2024-01-01T17:00:00Z", "window_end": "2024-01-01T17:00:00Z"},
        "window_end",
        "empty-window",
    ),
    bad(
        "find_common_free_slots",
        {"busy_starts": ["2024-01-01T09:00:00Z"], "busy_ends": [], "window_start": "2024-01-01T08:00:00Z", "window_end": "2024-01-01T17:00:00Z"},
        "busy_ends",
        "length-mismatch",
    ),
    bad(
        "find_common_free_slots",
        {"busy_starts": ["2024-01-01T10:00:00Z"], "busy_ends": ["2024-01-01T09:00:00Z"], "window_start": "2024-01-01T08:00:00Z", "window_end": "2024-01-01T17:00:00Z"},
        "busy_ends",
        "busy-start-after-end",
    ),
    invalid(
        "find_common_free_slots",
        {"busy_starts": [], "busy_ends": [], "window_start": "2024-01-01T08:00:00Z", "window_end": "2024-01-01T17:00:00Z", "minimum_minutes": 0},
        "minimum_minutes",
        "zero-minimum",
    ),
    bad("sort_date_strings", {"dates": ["2024-01-01", "not a date"]}, "dates", "unparseable"),
    invalid("sort_date_strings", {"dates": ["1" * 201]}, "dates", "item-over-phrase-cap"),
    # A.11 timestamps_durations
    bad("unix_timestamp_to_datetime", {"timestamp": 253402300800}, "timestamp", "year-10000"),
    bad("unix_timestamp_to_datetime", {"timestamp": -62135596801}, "timestamp", "before-year-1"),
    invalid("unix_timestamp_to_datetime", {"timestamp": 0, "utc_offset": "+5:30"}, "utc_offset", "offset-pattern"),
    bad("convert_utc_offset", {"moment": "9999-12-31T23:00:00Z", "to_offset": "+02:00"}, "to_offset", "past-year-9999"),
    bad("add_duration_to_datetime", {"moment": "9999-12-31T00:00:00Z", "days": 1}, "days", "past-year-9999"),
    invalid("format_duration", {"seconds": 1000000000001}, "seconds", "over-duration-bound"),
    bad("parse_duration_text", {"text": "P1M"}, "text", "iso-month-varies"),
    bad("parse_duration_text", {"text": "P1Y2D"}, "text", "iso-year-varies"),
    bad("parse_duration_text", {"text": "soon"}, "text", "unknown-form"),
    invalid("parse_duration_text", {"text": ""}, "text", "empty"),
    bad("minutes_between_times", {"start_time": "09:00+02:00", "end_time": "10:00"}, "start_time", "start-has-offset"),
    bad("minutes_between_times", {"start_time": "09:00Z", "end_time": "10:00Z"}, "start_time", "both-offsets-start-first"),
    bad("minutes_between_times", {"start_time": "09:00", "end_time": "10:00-05:00"}, "end_time", "end-has-offset"),
    invalid("minutes_between_times", {"start_time": "24:00", "end_time": "10:00"}, "start_time", "hour-24"),
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_time_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_time_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


def test_list_dates_in_range_stops_at_the_item_cap(tool_runner: ToolRunner) -> None:
    # 2024 through 2027 hold 366 + 365 + 365 + 365 = 1,461 dates; only the first 1,000 come back (INV-17).
    output = tool_runner.output("list_dates_in_range", {"start_date": "2024-01-01", "end_date": "2027-12-31"})
    assert output["count"] == 1461
    assert output["truncated"] is True
    assert output["dates"] == consecutive_dates("2024-01-01", 1000)
    assert output["dates"][-1] == "2026-09-26"


def test_generate_recurring_dates_counts_past_the_item_cap(tool_runner: ToolRunner) -> None:
    # 2000-01-01 through 2009-12-31 is 3,653 days (three leap years); count reports all of them arithmetically.
    output = tool_runner.output("generate_recurring_dates", {"start_date": "2000-01-01", "frequency": "daily", "until_date": "2009-12-31"})
    assert output["count"] == 3653
    assert output["truncated"] is True
    assert output["dates"] == consecutive_dates("2000-01-01", 1000)
    assert output["dates"][-1] == "2002-09-26"


def test_generate_recurring_dates_counts_a_long_weekly_run_without_listing_it(tool_runner: ToolRunner) -> None:
    # From 0001-01-01 every 7 days until 9999-12-31: 3,652,059 days hold 521,723 starts of a 7-day step (521,722 full steps plus the first date).
    output = tool_runner.output("generate_recurring_dates", {"start_date": "0001-01-01", "frequency": "weekly", "until_date": "9999-12-31"})
    assert output["count"] == 521723
    assert output["truncated"] is True
    assert output["dates"] == consecutive_dates("0001-01-01", 1000, 7)
