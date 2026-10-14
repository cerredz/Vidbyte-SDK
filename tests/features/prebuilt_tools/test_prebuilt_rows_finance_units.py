"""FILE: tests/features/prebuilt_tools/test_prebuilt_rows_finance_units.py

PURPOSE: Exact-output and error cases for every Appendix A row of the finance (A.7) and unit_conversion (A.8) categories, run through FunctionTool.execute as a model would call them.
ROLE IN CODEBASE: Row-level acceptance tests (AC-11) for FinanceToolFunctions and UnitConversionToolFunctions, reached only through PrebuiltTools via the tool_runner fixture in tests/features/prebuilt_tools/conftest.py.
ARCHITECTURE NOTE: Money texts were computed by hand with Fraction and the 50-digit Decimal order of spec §9.2 item 16; unit results were computed in Fraction from the §9.2 factor strings, a route independent of any float multiplication order; floats compare with the §9.2 item 5 rule.
FUNCTION INVENTORY: test_finance_units_rows_return_documented_output checks SUCCESS_CASES; test_finance_units_rows_reject_bad_input checks FAILURE_CASES; test_unit_factor_matches_spec_table converts one of every unit into its base unit; test_loan_totals_follow_the_amortization_schedule ties loan_payment_amount to amortization_schedule; test_thirty_year_schedule_pays_off_exactly checks a full 360-month schedule.
COMMON MODIFICATION PATTERNS: Add a row case as ok(...), bad(...), or invalid(...) in the list for its category; derive a new money value with Fraction and one half-up rounding to cents, never with float arithmetic.
WHAT NOT TO DO IN THIS FILE: 1. Do not compute an expected value by calling a prebuilt tool or importing vidbyte.tools.builtins.prebuilt; the expectation must stay independent. 2. Do not compare money texts approximately; §9.2 item 16 makes them exact.
KNOWN EDGE CASES: 1740.00 at 6.1% gives a period interest of exactly 8.845, which half-up rounding makes 8.85 (a binary 6.1 gives 8.84). 2.675 and 100.005 must round half-up to 2.68 and 100.01 through Decimal(repr(x)). Largest-remainder ties go to the lower index. irr_percent has its own 1e-9 absolute tolerance.
RELATED DOCS: tests/features/prebuilt_tools/FEATURE.md; docs/spec/prebuilt-agent-tools/spec.md (Appendix A.7, A.8; §9.2 items 5 and 16; unit factor tables)
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/prebuilt_tools/test_prebuilt_rows_finance_units.py
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

import pytest

from tests.features.prebuilt_tools.prebuilt_tool_harness import Close, FailureCase, SuccessCase, ToolRunner, bad, invalid, ok


def schedule_row(month: int, payment: str, principal: str, interest: str, balance: str) -> dict[str, Any]:
    """One amortization_schedule entry with the five documented keys."""
    return {"month": month, "payment": payment, "principal": principal, "interest": interest, "balance": balance}


def share(label: str, value: float, percent: str) -> dict[str, Any]:
    """One percentage_breakdown share with the three documented keys."""
    return {"label": label, "value": value, "percent": percent}


def converted(value: float, unit: str) -> dict[str, Any]:
    """The documented output of every unit conversion tool."""
    return {"value": value, "unit": unit}


FINANCE_SUCCESS_CASES = [
    # compound_interest_future_value: FV in a 50-digit Decimal context, rounded half-up to cents once.
    ok(
        "compound_interest_future_value",
        {"principal": 1000, "annual_rate_percent": 5, "years": 10, "compounding": "annually"},
        {"future_value": "1628.89", "interest_earned": "628.89"},
        "annual",
    ),
    ok(
        "compound_interest_future_value",
        {"principal": 1000, "annual_rate_percent": 5, "years": 10},
        {"future_value": "1647.01", "interest_earned": "647.01"},
        "default-monthly",
    ),
    ok(
        "compound_interest_future_value",
        {"principal": 1000, "annual_rate_percent": 5, "years": 10, "compounding": "continuously"},
        {"future_value": "1648.72", "interest_earned": "648.72"},
        "continuous",
    ),
    ok(
        "compound_interest_future_value",
        {"principal": 1000, "annual_rate_percent": 8, "years": 1, "compounding": "quarterly"},
        {"future_value": "1082.43", "interest_earned": "82.43"},
        "quarterly",
    ),
    ok(
        "compound_interest_future_value",
        {"principal": 2500, "annual_rate_percent": 3.5, "years": 2.5, "compounding": "semiannually"},
        {"future_value": "2726.54", "interest_earned": "226.54"},
        "semiannual-fractional-years",
    ),
    ok(
        "compound_interest_future_value",
        {"principal": 1000, "annual_rate_percent": 5, "years": 1, "compounding": "weekly"},
        {"future_value": "1051.25", "interest_earned": "51.25"},
        "weekly",
    ),
    ok(
        "compound_interest_future_value",
        {"principal": 1000, "annual_rate_percent": 5, "years": 1, "compounding": "daily"},
        {"future_value": "1051.27", "interest_earned": "51.27"},
        "daily",
    ),
    ok(
        "compound_interest_future_value",
        {"principal": 1000, "annual_rate_percent": -10, "years": 1, "compounding": "annually"},
        {"future_value": "900.00", "interest_earned": "-100.00"},
        "negative-rate",
    ),
    ok(
        "compound_interest_future_value",
        {"principal": 100.005, "annual_rate_percent": 5, "years": 0},
        {"future_value": "100.01", "interest_earned": "0.00"},
        "principal-rounds-half-up-from-shortest-text",
    ),
    ok(
        "compound_interest_future_value",
        {"principal": 2.675, "annual_rate_percent": 5, "years": 0, "compounding": "annually"},
        {"future_value": "2.68", "interest_earned": "0.00"},
        "principal-2.675-stays-exact",
    ),
    # loan_payment_amount: 200000 at 6% over 360 months is the published 1199.10 payment.
    ok(
        "loan_payment_amount",
        {"principal": 200000, "annual_rate_percent": 6, "term_months": 360},
        {"monthly_payment": "1199.10", "final_payment": "1200.14", "total_paid": "431677.04", "total_interest": "231677.04"},
        "thirty-year",
    ),
    ok(
        "loan_payment_amount",
        {"principal": 1000, "annual_rate_percent": 0, "term_months": 3},
        {"monthly_payment": "333.33", "final_payment": "333.34", "total_paid": "1000.00", "total_interest": "0.00"},
        "zero-rate-last-payment-absorbs-cents",
    ),
    ok(
        "loan_payment_amount",
        {"principal": 1000, "annual_rate_percent": 12, "term_months": 2},
        {"monthly_payment": "507.51", "final_payment": "507.51", "total_paid": "1015.02", "total_interest": "15.02"},
        "two-months",
    ),
    ok(
        "loan_payment_amount",
        {"principal": 1740, "annual_rate_percent": 6.1, "term_months": 1},
        {"monthly_payment": "1748.85", "final_payment": "1748.85", "total_paid": "1748.85", "total_interest": "8.85"},
        "interest-tie-8.845-rounds-up",
    ),
    ok(
        "loan_payment_amount",
        {"principal": 1740, "annual_rate_percent": 6.1, "term_months": 3},
        {"monthly_payment": "585.91", "final_payment": "585.90", "total_paid": "1757.72", "total_interest": "17.72"},
        "three-months-short-final",
    ),
    ok(
        "loan_payment_amount",
        {"principal": 0.06, "annual_rate_percent": 0, "term_months": 4},
        {"monthly_payment": "0.02", "final_payment": "0.02", "total_paid": "0.06", "total_interest": "0.00"},
        "paid-off-before-term",
    ),
    ok(
        "loan_payment_amount",
        {"principal": 2.675, "annual_rate_percent": 0, "term_months": 1},
        {"monthly_payment": "2.68", "final_payment": "2.68", "total_paid": "2.68", "total_interest": "0.00"},
        "principal-2.675-rounds-half-up",
    ),
    # amortization_schedule: interest per month is balance x rate / 1200, exact, then half-up to cents.
    ok(
        "amortization_schedule",
        {"principal": 1740, "annual_rate_percent": 6.1, "term_months": 1},
        {"monthly_payment": "1748.85", "schedule": [schedule_row(1, "1748.85", "1740.00", "8.85", "0.00")]},
        "interest-tie-8.845",
    ),
    ok(
        "amortization_schedule",
        {"principal": 1740, "annual_rate_percent": 6.1, "term_months": 2},
        {
            "monthly_payment": "876.64",
            "schedule": [
                schedule_row(1, "876.64", "867.79", "8.85", "872.21"),
                schedule_row(2, "876.64", "872.21", "4.43", "0.00"),
            ],
        },
        "two-months-tie-first",
    ),
    ok(
        "amortization_schedule",
        {"principal": 1740, "annual_rate_percent": 6.1, "term_months": 3},
        {
            "monthly_payment": "585.91",
            "schedule": [
                schedule_row(1, "585.91", "577.06", "8.85", "1162.94"),
                schedule_row(2, "585.91", "580.00", "5.91", "582.94"),
                schedule_row(3, "585.90", "582.94", "2.96", "0.00"),
            ],
        },
        "three-months",
    ),
    ok(
        "amortization_schedule",
        {"principal": 1000, "annual_rate_percent": 0, "term_months": 3},
        {
            "monthly_payment": "333.33",
            "schedule": [
                schedule_row(1, "333.33", "333.33", "0.00", "666.67"),
                schedule_row(2, "333.33", "333.33", "0.00", "333.34"),
                schedule_row(3, "333.34", "333.34", "0.00", "0.00"),
            ],
        },
        "zero-rate",
    ),
    ok(
        "amortization_schedule",
        {"principal": 0.06, "annual_rate_percent": 0, "term_months": 4},
        {
            "monthly_payment": "0.02",
            "schedule": [
                schedule_row(1, "0.02", "0.02", "0.00", "0.04"),
                schedule_row(2, "0.02", "0.02", "0.00", "0.02"),
                schedule_row(3, "0.02", "0.02", "0.00", "0.00"),
            ],
        },
        "ends-when-balance-reaches-zero",
    ),
    # net_present_value: t starts at 0, so -100 + 60/1.1 + 60/1.21 = 500/121 (a spreadsheet NPV would give 500/133.1).
    ok("net_present_value", {"rate_percent": 10, "cash_flows": [-100, 60, 60]}, {"npv": 500 / 121}, "first-flow-undiscounted"),
    ok("net_present_value", {"rate_percent": 5, "cash_flows": [42.5]}, {"npv": 42.5}, "single-flow"),
    ok("net_present_value", {"rate_percent": 0, "cash_flows": [1, 2, 3.5]}, {"npv": 6.5}, "zero-rate"),
    # internal_rate_of_return: roots from a 60-digit Decimal Newton iteration, a different route from the bisection.
    ok("internal_rate_of_return", {"cash_flows": [-100, 110]}, {"irr_percent": Close(10.0, 1e-9)}, "ten-percent"),
    ok("internal_rate_of_return", {"cash_flows": [100, -110]}, {"irr_percent": Close(10.0, 1e-9)}, "reversed-signs"),
    ok("internal_rate_of_return", {"cash_flows": [-100, 50, 60]}, {"irr_percent": Close(6.394102980498532, 1e-9)}, "quadratic-root"),
    ok(
        "internal_rate_of_return",
        {"cash_flows": [-1000, 300, 400, 500]},
        {"irr_percent": Close(8.896339469334994, 1e-9)},
        "four-flows",
    ),
    # compound_annual_growth_rate: ((end / start) ** (1 / years) - 1) * 100.
    ok("compound_annual_growth_rate", {"start_value": 100, "end_value": 200, "years": 2}, {"cagr_percent": 41.42135623730950}, "doubling"),
    ok("compound_annual_growth_rate", {"start_value": 100, "end_value": 121, "years": 2}, {"cagr_percent": 10.0}, "ten-percent"),
    ok("compound_annual_growth_rate", {"start_value": 50, "end_value": 0, "years": 3}, {"cagr_percent": -100.0}, "total-loss"),
    # percentage_change: divides by abs(old) so a drop from a negative value stays negative.
    ok("percentage_change", {"old_value": 50, "new_value": 75}, {"change_percent": 50.0, "difference": 25.0}, "rise"),
    ok("percentage_change", {"old_value": -50, "new_value": -75}, {"change_percent": -50.0, "difference": -25.0}, "drop-from-negative"),
    ok("percentage_change", {"old_value": -50, "new_value": -25}, {"change_percent": 50.0, "difference": 25.0}, "rise-from-negative"),
    # percentage_breakdown: floor to the places, then largest remainders, ties to the lower index.
    ok(
        "percentage_breakdown",
        {"labels": ["a", "b", "c"], "values": [1, 1, 1]},
        {"total": 3.0, "shares": [share("a", 1.0, "33.4"), share("b", 1.0, "33.3"), share("c", 1.0, "33.3")]},
        "default-one-place-tie-to-first",
    ),
    ok(
        "percentage_breakdown",
        {"labels": ["a", "b", "c", "d"], "values": [1, 2, 3, 4], "decimal_places": 0},
        {"total": 10.0, "shares": [share("a", 1.0, "10"), share("b", 2.0, "20"), share("c", 3.0, "30"), share("d", 4.0, "40")]},
        "zero-places-no-point",
    ),
    ok(
        "percentage_breakdown",
        {"labels": ["x", "y", "z"], "values": [2, 3, 4], "decimal_places": 0},
        {"total": 9.0, "shares": [share("x", 2.0, "22"), share("y", 3.0, "33"), share("z", 4.0, "45")]},
        "largest-remainder-wins",
    ),
    ok(
        "percentage_breakdown",
        {"labels": ["p", "q"], "values": [0.1, 0.2], "decimal_places": 2},
        {"total": 0.30000000000000004, "shares": [share("p", 0.1, "33.33"), share("q", 0.2, "66.67")]},
        "float-values-from-shortest-text",
    ),
    ok(
        "percentage_breakdown",
        {"labels": ["a", "b", "c", "d", "e", "f", "g"], "values": [1, 1, 1, 1, 1, 1, 1], "decimal_places": 2},
        {
            "total": 7.0,
            "shares": [
                share("a", 1.0, "14.29"),
                share("b", 1.0, "14.29"),
                share("c", 1.0, "14.29"),
                share("d", 1.0, "14.29"),
                share("e", 1.0, "14.28"),
                share("f", 1.0, "14.28"),
                share("g", 1.0, "14.28"),
            ],
        },
        "four-of-seven-ties-to-lower-indexes",
    ),
    # allocate_amount: parts sum to exactly the amount.
    ok("allocate_amount", {"amount": "100.00", "weights": [1, 1, 1]}, {"allocations": ["33.34", "33.33", "33.33"]}, "thirds-tie-first"),
    ok("allocate_amount", {"amount": "10", "weights": [1, 2]}, {"allocations": ["3.33", "6.67"]}, "largest-remainder"),
    ok("allocate_amount", {"amount": "0.05", "weights": [1, 1]}, {"allocations": ["0.03", "0.02"]}, "half-cent-tie-to-first"),
    ok("allocate_amount", {"amount": "7", "weights": [1, 1], "decimal_places": 0}, {"allocations": ["4", "3"]}, "zero-places"),
    ok("allocate_amount", {"amount": "3", "weights": [0.1, 0.2]}, {"allocations": ["1.00", "2.00"]}, "float-weights"),
    ok("allocate_amount", {"amount": "1", "weights": [1, 1, 1], "decimal_places": 3}, {"allocations": ["0.334", "0.333", "0.333"]}, "three-places"),
    # split_tax_inclusive_amount: net = gross / (1 + rate / 100), exact, then half-up to cents; tax = gross - net.
    ok("split_tax_inclusive_amount", {"gross_amount": "119.00", "tax_rate_percent": 19}, {"net_amount": "100.00", "tax_amount": "19.00"}, "exact"),
    ok("split_tax_inclusive_amount", {"gross_amount": "119", "tax_rate_percent": 19}, {"net_amount": "100.00", "tax_amount": "19.00"}, "integer-gross"),
    ok("split_tax_inclusive_amount", {"gross_amount": "10.00", "tax_rate_percent": 7.5}, {"net_amount": "9.30", "tax_amount": "0.70"}, "rounded"),
    ok("split_tax_inclusive_amount", {"gross_amount": "0.01", "tax_rate_percent": 100}, {"net_amount": "0.01", "tax_amount": "0.00"}, "half-cent-rounds-up"),
    ok("split_tax_inclusive_amount", {"gross_amount": "2.50", "tax_rate_percent": 100}, {"net_amount": "1.25", "tax_amount": "1.25"}, "halves"),
    ok("split_tax_inclusive_amount", {"gross_amount": "100.00", "tax_rate_percent": 0}, {"net_amount": "100.00", "tax_amount": "0.00"}, "zero-rate"),
]

UNIT_SUCCESS_CASES = [
    ok("convert_length", {"value": 1, "from_unit": "mile", "to_unit": "kilometer"}, converted(1.609344, "kilometer"), "mile-to-km"),
    ok("convert_length", {"value": 12, "from_unit": "inch", "to_unit": "foot"}, converted(1.0, "foot"), "inches-to-foot"),
    ok("convert_length", {"value": -5, "from_unit": "meter", "to_unit": "centimeter"}, converted(-500.0, "centimeter"), "negative-offset"),
    ok("convert_length", {"value": 1, "from_unit": "nautical_mile", "to_unit": "mile"}, converted(1.1507794480235425, "mile"), "nautical"),
    ok("convert_mass", {"value": 1, "from_unit": "pound", "to_unit": "kilogram"}, converted(0.45359237, "kilogram"), "pound"),
    ok("convert_mass", {"value": 1, "from_unit": "stone", "to_unit": "pound"}, converted(14.0, "pound"), "stone"),
    ok("convert_mass", {"value": 1, "from_unit": "long_ton", "to_unit": "short_ton"}, converted(1.12, "short_ton"), "tons"),
    ok("convert_temperature", {"value": 100, "from_unit": "celsius", "to_unit": "fahrenheit"}, converted(212.0, "fahrenheit"), "boiling"),
    ok("convert_temperature", {"value": -40, "from_unit": "celsius", "to_unit": "fahrenheit"}, converted(-40.0, "fahrenheit"), "crossover"),
    ok("convert_temperature", {"value": 32, "from_unit": "fahrenheit", "to_unit": "kelvin"}, converted(273.15, "kelvin"), "freezing-kelvin"),
    ok("convert_temperature", {"value": 491.67, "from_unit": "rankine", "to_unit": "celsius"}, converted(0.0, "celsius"), "rankine"),
    ok("convert_temperature", {"value": -273.15, "from_unit": "celsius", "to_unit": "kelvin"}, converted(0.0, "kelvin"), "absolute-zero-allowed"),
    ok("convert_volume", {"value": 1, "from_unit": "us_gallon", "to_unit": "liter"}, converted(3.785411784, "liter"), "us-gallon"),
    ok(
        "convert_volume",
        {"value": 1, "from_unit": "imperial_gallon", "to_unit": "us_gallon"},
        converted(1.200949925504855, "us_gallon"),
        "imperial-is-distinct",
    ),
    ok("convert_volume", {"value": 1, "from_unit": "us_cup", "to_unit": "us_tablespoon"}, converted(16.0, "us_tablespoon"), "cup"),
    ok("convert_volume", {"value": 1, "from_unit": "cubic_foot", "to_unit": "cubic_inch"}, converted(1728.0, "cubic_inch"), "cubic"),
    ok("convert_area", {"value": 1, "from_unit": "acre", "to_unit": "square_foot"}, converted(43560.0, "square_foot"), "acre"),
    ok("convert_area", {"value": 1, "from_unit": "hectare", "to_unit": "acre"}, converted(2.4710538146716536, "acre"), "hectare"),
    ok("convert_area", {"value": 1, "from_unit": "square_mile", "to_unit": "acre"}, converted(640.0, "acre"), "square-mile"),
    ok(
        "convert_speed",
        {"value": 100, "from_unit": "kilometers_per_hour", "to_unit": "meters_per_second"},
        converted(27.77777777777778, "meters_per_second"),
        "kmh",
    ),
    ok("convert_speed", {"value": 1, "from_unit": "knots", "to_unit": "kilometers_per_hour"}, converted(1.852, "kilometers_per_hour"), "knot"),
    ok("convert_speed", {"value": 60, "from_unit": "miles_per_hour", "to_unit": "feet_per_second"}, converted(88.0, "feet_per_second"), "mph"),
    ok("convert_duration", {"value": 1, "from_unit": "week", "to_unit": "second"}, converted(604800.0, "second"), "week"),
    ok("convert_duration", {"value": 90, "from_unit": "minute", "to_unit": "hour"}, converted(1.5, "hour"), "minutes"),
    ok("convert_duration", {"value": 1, "from_unit": "nanosecond", "to_unit": "second"}, converted(1e-09, "second"), "nanosecond"),
    ok("convert_energy", {"value": 1, "from_unit": "kilowatt_hour", "to_unit": "megajoule"}, converted(3.6, "megajoule"), "kwh"),
    ok(
        "convert_energy",
        {"value": 1, "from_unit": "kilocalorie", "to_unit": "british_thermal_unit"},
        converted(3.9656668313909194, "british_thermal_unit"),
        "kcal-to-btu",
    ),
    ok("convert_energy", {"value": 1, "from_unit": "electronvolt", "to_unit": "joule"}, converted(1.602176634e-19, "joule"), "electronvolt"),
    ok(
        "convert_fuel_economy",
        {"value": 10, "from_unit": "liters_per_100_kilometers", "to_unit": "kilometers_per_liter"},
        converted(10.0, "kilometers_per_liter"),
        "inverse-unit",
    ),
    ok(
        "convert_fuel_economy",
        {"value": 30, "from_unit": "miles_per_us_gallon", "to_unit": "liters_per_100_kilometers"},
        converted(7.840486111111111, "liters_per_100_kilometers"),
        "mpg-to-l100",
    ),
    ok(
        "convert_fuel_economy",
        {"value": 10, "from_unit": "liters_per_100_kilometers", "to_unit": "miles_per_us_gallon"},
        converted(23.52145833333333, "miles_per_us_gallon"),
        "l100-to-mpg",
    ),
    ok(
        "convert_fuel_economy",
        {"value": 5, "from_unit": "liters_per_100_kilometers", "to_unit": "liters_per_100_kilometers"},
        converted(5.0, "liters_per_100_kilometers"),
        "inverse-twice-is-identity",
    ),
    ok(
        "convert_fuel_economy",
        {"value": 1, "from_unit": "miles_per_imperial_gallon", "to_unit": "miles_per_us_gallon"},
        converted(0.8326741846289889, "miles_per_us_gallon"),
        "imperial-to-us",
    ),
    ok("convert_data_size", {"value": 1, "from_unit": "kibibyte", "to_unit": "byte"}, converted(1024.0, "byte"), "kibibyte"),
    ok("convert_data_size", {"value": 1, "from_unit": "byte", "to_unit": "bit"}, converted(8.0, "bit"), "bits"),
    ok("convert_data_size", {"value": 1, "from_unit": "gigabyte", "to_unit": "gibibyte"}, converted(0.9313225746154785, "gibibyte"), "gb-to-gib"),
    ok("convert_data_size", {"value": 1, "from_unit": "megabit", "to_unit": "kilobyte"}, converted(125.0, "kilobyte"), "megabit"),
]

SUCCESS_CASES = FINANCE_SUCCESS_CASES + UNIT_SUCCESS_CASES

FAILURE_CASES = [
    bad(
        "compound_interest_future_value",
        {"principal": 1e15, "annual_rate_percent": 1000, "years": 1000, "compounding": "annually"},
        "years",
        "future-value-overflow-guard",
    ),
    invalid("compound_interest_future_value", {"principal": 1000, "annual_rate_percent": -100, "years": 1}, "annual_rate_percent", "rate-minus-100"),
    invalid("compound_interest_future_value", {"principal": -1, "annual_rate_percent": 5, "years": 1}, "principal", "negative-principal"),
    invalid("loan_payment_amount", {"principal": 0, "annual_rate_percent": 5, "term_months": 12}, "principal", "zero-principal"),
    invalid("loan_payment_amount", {"principal": 1000, "annual_rate_percent": 5, "term_months": 601}, "term_months", "term-over-cap"),
    invalid("amortization_schedule", {"principal": 1000, "annual_rate_percent": 5, "term_months": 0}, "term_months", "zero-term"),
    bad("net_present_value", {"rate_percent": 1000, "cash_flows": [1.0] * 400}, "rate_percent", "power-overflows"),
    bad("net_present_value", {"rate_percent": -99.99, "cash_flows": [1.0] * 100}, "rate_percent", "power-underflows-to-zero"),
    invalid("net_present_value", {"rate_percent": 5, "cash_flows": []}, "cash_flows", "no-flows"),
    invalid("net_present_value", {"rate_percent": -100, "cash_flows": [1]}, "rate_percent", "rate-minus-100"),
    bad("internal_rate_of_return", {"cash_flows": [100, 200]}, "cash_flows", "no-negative-flow"),
    bad("internal_rate_of_return", {"cash_flows": [0, 0]}, "cash_flows", "all-zero"),
    bad("internal_rate_of_return", {"cash_flows": [-100, 1e-9]}, "cash_flows", "no-sign-change-in-grid"),
    invalid("internal_rate_of_return", {"cash_flows": [-100]}, "cash_flows", "single-flow"),
    invalid("compound_annual_growth_rate", {"start_value": 0, "end_value": 10, "years": 1}, "start_value", "zero-start"),
    invalid("compound_annual_growth_rate", {"start_value": 1, "end_value": 10, "years": 0}, "years", "zero-years"),
    bad("percentage_change", {"old_value": 0, "new_value": 5}, "old_value", "zero-old-value"),
    bad("percentage_breakdown", {"labels": ["a", "b"], "values": [1]}, "values", "length-mismatch"),
    bad("percentage_breakdown", {"labels": ["a", "b"], "values": [1, -1]}, "values", "negative-value"),
    bad("percentage_breakdown", {"labels": ["a", "b"], "values": [0, 0]}, "values", "zero-total"),
    invalid("percentage_breakdown", {"labels": ["a"], "values": [1], "decimal_places": 11}, "decimal_places", "places-over-cap"),
    bad("allocate_amount", {"amount": "-5", "weights": [1, 1]}, "amount", "negative-amount"),
    bad("allocate_amount", {"amount": "1.005", "weights": [1, 1]}, "amount", "too-many-fraction-digits"),
    bad("allocate_amount", {"amount": "10", "weights": [1, -1]}, "weights", "negative-weight"),
    bad("allocate_amount", {"amount": "10", "weights": [0, 0]}, "weights", "zero-total-weight"),
    invalid("allocate_amount", {"amount": "1e3", "weights": [1]}, "amount", "exponent-not-dectext"),
    bad("split_tax_inclusive_amount", {"gross_amount": "-1.00", "tax_rate_percent": 10}, "gross_amount", "negative-gross"),
    bad("split_tax_inclusive_amount", {"gross_amount": "1.005", "tax_rate_percent": 10}, "gross_amount", "three-fraction-digits"),
    bad("split_tax_inclusive_amount", {"gross_amount": "1000000000000000.01", "tax_rate_percent": 10}, "gross_amount", "above-money-cap"),
    invalid("split_tax_inclusive_amount", {"gross_amount": "12", "tax_rate_percent": -1}, "tax_rate_percent", "negative-rate"),
    bad("convert_length", {"value": 1e308, "from_unit": "meter", "to_unit": "nanometer"}, "value", "non-finite-result"),
    invalid("convert_length", {"value": 1, "from_unit": "furlong", "to_unit": "meter"}, "from_unit", "unknown-unit"),
    bad("convert_data_size", {"value": 1e308, "from_unit": "petabyte", "to_unit": "bit"}, "value", "non-finite-result"),
    bad("convert_temperature", {"value": -300, "from_unit": "celsius", "to_unit": "kelvin"}, "value", "below-absolute-zero-celsius"),
    bad("convert_temperature", {"value": -1, "from_unit": "kelvin", "to_unit": "celsius"}, "value", "negative-kelvin"),
    bad("convert_temperature", {"value": -460, "from_unit": "fahrenheit", "to_unit": "celsius"}, "value", "below-absolute-zero-fahrenheit"),
    invalid("convert_temperature", {"value": 1, "from_unit": "celsius", "to_unit": "reaumur"}, "to_unit", "unknown-unit"),
    bad("convert_fuel_economy", {"value": 0, "from_unit": "miles_per_us_gallon", "to_unit": "kilometers_per_liter"}, "value", "zero"),
    bad("convert_fuel_economy", {"value": -5, "from_unit": "liters_per_100_kilometers", "to_unit": "kilometers_per_liter"}, "value", "negative"),
]

# Spec §9.2 unit factor tables: (tool, base unit, ((unit, size of one unit in the base unit as Fraction text), ...)).
UNIT_FACTOR_TABLES = (
    (
        "convert_length",
        "meter",
        (
            ("nanometer", "0.000000001"), ("micrometer", "0.000001"), ("millimeter", "0.001"), ("centimeter", "0.01"), ("meter", "1"),
            ("kilometer", "1000"), ("inch", "0.0254"), ("foot", "0.3048"), ("yard", "0.9144"), ("mile", "1609.344"), ("nautical_mile", "1852"),
        ),
    ),
    (
        "convert_mass",
        "kilogram",
        (
            ("milligram", "0.000001"), ("gram", "0.001"), ("kilogram", "1"), ("metric_ton", "1000"), ("ounce", "0.028349523125"),
            ("pound", "0.45359237"), ("stone", "6.35029318"), ("short_ton", "907.18474"), ("long_ton", "1016.0469088"),
        ),
    ),
    (
        "convert_volume",
        "liter",
        (
            ("milliliter", "0.001"), ("liter", "1"), ("cubic_centimeter", "0.001"), ("cubic_meter", "1000"), ("cubic_inch", "0.016387064"),
            ("cubic_foot", "28.316846592"), ("us_teaspoon", "0.00492892159375"), ("us_tablespoon", "0.01478676478125"),
            ("us_fluid_ounce", "0.0295735295625"), ("us_cup", "0.2365882365"), ("us_pint", "0.473176473"), ("us_quart", "0.946352946"),
            ("us_gallon", "3.785411784"), ("imperial_fluid_ounce", "0.0284130625"), ("imperial_pint", "0.56826125"),
            ("imperial_quart", "1.1365225"), ("imperial_gallon", "4.54609"),
        ),
    ),
    (
        "convert_area",
        "square_meter",
        (
            ("square_millimeter", "0.000001"), ("square_centimeter", "0.0001"), ("square_meter", "1"), ("square_kilometer", "1000000"),
            ("hectare", "10000"), ("square_inch", "0.00064516"), ("square_foot", "0.09290304"), ("square_yard", "0.83612736"),
            ("acre", "4046.8564224"), ("square_mile", "2589988.110336"),
        ),
    ),
    (
        "convert_speed",
        "meters_per_second",
        (("meters_per_second", "1"), ("kilometers_per_hour", "5/18"), ("miles_per_hour", "0.44704"), ("knots", "463/900"), ("feet_per_second", "0.3048")),
    ),
    (
        "convert_duration",
        "second",
        (
            ("nanosecond", "1/1000000000"), ("microsecond", "1/1000000"), ("millisecond", "1/1000"), ("second", "1"), ("minute", "60"),
            ("hour", "3600"), ("day", "86400"), ("week", "604800"),
        ),
    ),
    (
        "convert_energy",
        "joule",
        (
            ("joule", "1"), ("kilojoule", "1000"), ("megajoule", "1000000"), ("calorie", "4.184"), ("kilocalorie", "4184"), ("watt_hour", "3600"),
            ("kilowatt_hour", "3600000"), ("british_thermal_unit", "1055.05585262"), ("electronvolt", "1.602176634e-19"),
        ),
    ),
    (
        "convert_data_size",
        "byte",
        (
            ("bit", "1/8"), ("byte", "1"), ("kilobyte", "1000"), ("megabyte", "1000000"), ("gigabyte", "1000000000"),
            ("terabyte", "1000000000000"), ("petabyte", "1000000000000000"), ("kibibyte", "1024"), ("mebibyte", "1048576"),
            ("gibibyte", "1073741824"), ("tebibyte", "1099511627776"), ("pebibyte", "1125899906842624"), ("kilobit", "125"),
            ("megabit", "125000"), ("gigabit", "125000000"),
        ),
    ),
)

UNIT_FACTOR_CASES = [
    pytest.param(tool, unit, base, float(Fraction(factor)), id=f"{tool}-{unit}")
    for tool, base, factors in UNIT_FACTOR_TABLES
    for unit, factor in factors
]


@pytest.mark.parametrize("case", SUCCESS_CASES)
def test_finance_units_rows_return_documented_output(tool_runner: ToolRunner, case: SuccessCase) -> None:
    tool_runner.check_success(case)


@pytest.mark.parametrize("case", FAILURE_CASES)
def test_finance_units_rows_reject_bad_input(tool_runner: ToolRunner, case: FailureCase) -> None:
    tool_runner.check_failure(case)


@pytest.mark.parametrize(("tool", "unit", "base", "expected"), UNIT_FACTOR_CASES)
def test_unit_factor_matches_spec_table(tool_runner: ToolRunner, tool: str, unit: str, base: str, expected: float) -> None:
    # One of every unit, converted into the table's base unit, must equal that unit's exact §9.2 factor.
    output = tool_runner.output(tool, {"value": 1, "from_unit": unit, "to_unit": base})
    assert output == {"value": pytest.approx(expected, rel=1e-9, abs=1e-12), "unit": base}


@pytest.mark.parametrize(
    "arguments",
    [
        {"principal": 1740, "annual_rate_percent": 6.1, "term_months": 7},
        {"principal": 12345.67, "annual_rate_percent": 3.25, "term_months": 24},
        {"principal": 999.99, "annual_rate_percent": 0, "term_months": 7},
    ],
    ids=["tie-rate", "odd-principal", "zero-rate"],
)
def test_loan_totals_follow_the_amortization_schedule(tool_runner: ToolRunner, arguments: dict[str, Any]) -> None:
    # loan_payment_amount must report the schedule's own last payment and sum, not payment x term.
    loan = tool_runner.output("loan_payment_amount", arguments)
    schedule = tool_runner.output("amortization_schedule", arguments)
    payments = [Fraction(row["payment"]) for row in schedule["schedule"]]
    total = sum(payments, Fraction(0))
    assert loan["monthly_payment"] == schedule["monthly_payment"]
    assert loan["final_payment"] == schedule["schedule"][-1]["payment"]
    assert Fraction(loan["total_paid"]) == total
    assert Fraction(loan["total_interest"]) == total - Fraction(str(arguments["principal"]))
    assert [row["month"] for row in schedule["schedule"]] == list(range(1, len(payments) + 1))
    assert schedule["schedule"][-1]["balance"] == "0.00"


def test_thirty_year_schedule_pays_off_exactly(tool_runner: ToolRunner) -> None:
    # 200000 at 6% for 360 months: month 1 is the published 1000.00 interest and 199.10 principal.
    output = tool_runner.output("amortization_schedule", {"principal": 200000, "annual_rate_percent": 6, "term_months": 360})
    rows = output["schedule"]
    assert output["monthly_payment"] == "1199.10"
    assert len(rows) == 360
    assert rows[0] == schedule_row(1, "1199.10", "199.10", "1000.00", "199800.90")
    assert rows[358] == schedule_row(359, "1199.10", "1187.19", "11.91", "1194.17")
    assert rows[359] == schedule_row(360, "1200.14", "1194.17", "5.97", "0.00")
    for row in rows:
        assert Fraction(row["principal"]) + Fraction(row["interest"]) == Fraction(row["payment"])
    assert sum((Fraction(row["payment"]) for row in rows), Fraction(0)) == Fraction("431677.04")
