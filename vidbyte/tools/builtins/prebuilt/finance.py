"""FILE: vidbyte/tools/builtins/prebuilt/finance.py

PURPOSE: Defines FinanceToolFunctions, the ten prebuilt tools for money and rate questions: compound interest, the level loan payment and its totals, the amortization schedule, net present value, internal rate of return, compound annual growth rate, percentage change, percentage shares that sum to 100, exact allocation of an amount by weights, and splitting a tax-inclusive gross amount.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the FINANCE category is chosen. Builds on PrebuiltToolSupport in _support.py for decimal text, weights, paired lists, finite floats, and the argument error.
ARCHITECTURE NOTE: Money follows spec section 9.2 item 16. Float inputs enter exact arithmetic through their shortest text, every rational money step is exact in Fraction and kept in whole cents, and only compound growth runs in a 50-digit decimal context in the stated operation order. Each money output is rounded half-up to cents exactly once and written from an integer cent count, so -0.00 can never appear. The rate formulas (net present value, internal rate of return, growth rate, percentage change) are float formulas.
FUNCTION INVENTORY: compound_interest_future_value, loan_payment_amount, amortization_schedule, net_present_value, internal_rate_of_return, compound_annual_growth_rate, percentage_change, percentage_breakdown, allocate_amount, and split_tax_inclusive_amount are the tools; _future_value runs the decimal growth; _level_payment, _amortize, _half_up, and _money_text build loan money; _npv_at and _bisect_root drive the rate search; _largest_remainder and _unit_text build exact shares; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new money tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.7, and its entry in tool_functions; it keeps money in integer cents and writes it through _money_text. A change to a rounding rule changes section 9.2 item 16 first.
WHAT NOT TO DO IN THIS FILE: 1. Do not build a Decimal or Fraction from a float directly; use repr(x) so a value such as 2.675 stays exact. 2. Do not round a money value twice or round with float arithmetic or round(). 3. Do not use the host's decimal context; every decimal step runs inside PrebuiltToolSupport.decimal_context with PREBUILT_FINANCE_PRECISION. 4. Do not compute loan totals as payment times term; they come from the schedule.
KNOWN EDGE CASES: 1740.00 at 6.1 percent has a first-month interest of exactly 8.845, which half-up rounding makes 8.85. Cent rounding of the level payment can pay a loan off before its term, so the schedule ends at the first zero balance. A principal that rounds to 0.00 gives a single zero row. The rate search skips grid points whose powers overflow or vanish, which long series hit near both ends of the grid.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.7, section 9.2 items 5, 13, and 16, D-16); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_finance_units.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Sequence
from decimal import (
    ROUND_HALF_UP,
    Decimal,
    DecimalException,
)
from fractions import Fraction
from functools import partial
from types import MappingProxyType
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_DECIMAL_TEXT_PATTERN,
    PREBUILT_FINANCE_PRECISION,
    PREBUILT_IRR_BISECTION_STEPS,
    PREBUILT_IRR_GRID_POINTS,
    PREBUILT_IRR_GRID_START,
    PREBUILT_IRR_GRID_STEP,
    PREBUILT_IRR_TOLERANCE,
    PREBUILT_MAX_CASH_FLOWS,
    PREBUILT_MAX_DECIMAL_TEXT_CHARS,
    PREBUILT_MAX_FINANCE_YEARS,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_LOAN_MONTHS,
    PREBUILT_MAX_MONEY_AMOUNT,
    PREBUILT_MAX_RATE_PERCENT,
    PREBUILT_MAX_SHARE_PLACES,
    PREBUILT_MAX_SHORT_TEXT_CHARS,
)
from vidbyte.lib.enums.prebuilt_tools import CompoundingFrequency
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_LOWEST_RATE_PERCENT = -100
_PERCENT = 100
_CENTS_PER_UNIT = 100
_MONTHLY_RATE_DIVISOR = 1200
_MONEY_PLACES = 2
_HALF = Fraction(1, 2)
_CENT = Decimal("0.01")
_FUTURE_VALUE_CEILING = Decimal("1E+47")
_PERIODS_PER_YEAR = MappingProxyType(
    {
        CompoundingFrequency.ANNUALLY: 1,
        CompoundingFrequency.SEMIANNUALLY: 2,
        CompoundingFrequency.QUARTERLY: 4,
        CompoundingFrequency.MONTHLY: 12,
        CompoundingFrequency.WEEKLY: 52,
        CompoundingFrequency.DAILY: 365,
    }
)

_LOAN_PRINCIPAL_DESCRIPTION = "The amount borrowed, in any currency, as a number above zero and at most one quadrillion. It is first rounded half-up to whole cents from its shortest decimal text. Every payment, balance, and total uses the same currency unit. Zero or a negative amount fails validation."
_LOAN_RATE_DESCRIPTION = "The yearly interest rate in percent, not as a fraction of one, from zero to 1,000. The monthly rate is this value divided by 1,200, read exactly from its shortest decimal text. A rate of zero spreads the principal evenly across the months. A negative rate fails validation."
_LOAN_TERM_DESCRIPTION = "The number of monthly payments, from 1 to 600. The schedule never runs longer than this term. Cent rounding of the level payment can pay a small loan off a few months early. Fractional months are not accepted."
_FINITE_NUMBER = Annotated[float, Field(allow_inf_nan=False)]


class FinanceToolFunctions:
    """The finance category: compound interest, loans, discounted cash flows, growth rates, and exact shares."""

    @staticmethod
    def compound_interest_future_value(
        principal: Annotated[float, Field(description="The starting amount, in any currency, as a number from zero to one quadrillion. It is first rounded half-up to whole cents from its shortest decimal text. The interest earned is measured against this rounded amount. A negative amount fails validation.", allow_inf_nan=False, ge=0, le=PREBUILT_MAX_MONEY_AMOUNT)],
        annual_rate_percent: Annotated[float, Field(description="The yearly interest rate in percent, not as a fraction of one. It must be above minus 100 and at most 1,000, and a negative rate shrinks the amount. The rate is read exactly from its shortest decimal text. It is divided by the number of compounding periods per year.", allow_inf_nan=False, gt=_LOWEST_RATE_PERCENT, le=PREBUILT_MAX_RATE_PERCENT)],
        years: Annotated[float, Field(description="How many years the money grows, from zero to 1,000. Fractional years are allowed and compound over a fractional number of periods. Zero years gives back the rounded principal. A future value that reaches the overflow guard fails with an error naming this parameter.", allow_inf_nan=False, ge=0, le=PREBUILT_MAX_FINANCE_YEARS)],
        compounding: Annotated[CompoundingFrequency, Field(description="How often interest is added to the balance: annually, semiannually, quarterly, monthly, weekly, daily, or continuously. Weekly means 52 periods a year and daily means 365. Continuous compounding uses the exponential of the rate times the years. The default is monthly.")] = CompoundingFrequency.MONTHLY,
    ) -> PrebuiltToolOutput:
        """Compute the future value of a lump sum under compound interest and the interest earned on top of the principal, as money texts with two decimals. Use it for savings, deposit, or investment growth questions where an exact cent amount matters. Interest compounds annually, semiannually, quarterly, monthly, weekly, daily, or continuously, the growth runs in 50-digit decimal arithmetic, and the future value is rounded half-up to cents once. A future value of 10^47 or more fails with an error naming years."""
        # Round the principal to cents and grow it in the 50-digit
        # decimal context, then round the future value to cents once.
        start_cents, final_cents = FinanceToolFunctions._future_value(principal, annual_rate_percent, years, compounding)
        return {
            "future_value": FinanceToolFunctions._money_text(final_cents),
            "interest_earned": FinanceToolFunctions._money_text(final_cents - start_cents),
        }

    @staticmethod
    def loan_payment_amount(
        principal: Annotated[float, Field(description=_LOAN_PRINCIPAL_DESCRIPTION, allow_inf_nan=False, gt=0, le=PREBUILT_MAX_MONEY_AMOUNT)],
        annual_rate_percent: Annotated[float, Field(description=_LOAN_RATE_DESCRIPTION, allow_inf_nan=False, ge=0, le=PREBUILT_MAX_RATE_PERCENT)],
        term_months: Annotated[int, Field(description=_LOAN_TERM_DESCRIPTION, ge=1, le=PREBUILT_MAX_LOAN_MONTHS)],
    ) -> PrebuiltToolOutput:
        """Compute the fixed monthly payment of an amortizing loan with its final payment, total paid, and total interest, as money texts with two decimals. Use it for mortgage and loan questions that need exact cents, because the final payment and the totals come from the full month-by-month schedule rather than the payment times the term. The payment uses the standard annuity formula in exact rational arithmetic, rounded half-up to cents, and a zero rate divides the principal evenly. Inputs outside the schema bounds fail validation, and no valid input fails otherwise."""
        # Round the principal to cents and find the level payment.
        principal_cents = FinanceToolFunctions._half_up(Fraction(repr(principal)) * _CENTS_PER_UNIT)
        monthly_interest_fraction = Fraction(repr(annual_rate_percent)) / _MONTHLY_RATE_DIVISOR
        payment_cents = FinanceToolFunctions._half_up(FinanceToolFunctions._level_payment(principal_cents, monthly_interest_fraction, term_months))

        # Walk the schedule so the final payment and the totals are the
        # ones the loan really has.
        rows = FinanceToolFunctions._amortize(principal_cents, monthly_interest_fraction, term_months, payment_cents)
        total_cents = sum(row[1] for row in rows)
        return {
            "monthly_payment": FinanceToolFunctions._money_text(payment_cents),
            "final_payment": FinanceToolFunctions._money_text(rows[-1][1]),
            "total_paid": FinanceToolFunctions._money_text(total_cents),
            "total_interest": FinanceToolFunctions._money_text(total_cents - principal_cents),
        }

    @staticmethod
    def amortization_schedule(
        principal: Annotated[float, Field(description=_LOAN_PRINCIPAL_DESCRIPTION, allow_inf_nan=False, gt=0, le=PREBUILT_MAX_MONEY_AMOUNT)],
        annual_rate_percent: Annotated[float, Field(description=_LOAN_RATE_DESCRIPTION, allow_inf_nan=False, ge=0, le=PREBUILT_MAX_RATE_PERCENT)],
        term_months: Annotated[int, Field(description=_LOAN_TERM_DESCRIPTION, ge=1, le=PREBUILT_MAX_LOAN_MONTHS)],
    ) -> PrebuiltToolOutput:
        """List every monthly payment of an amortizing loan with its principal part, interest part, and remaining balance, plus the level monthly payment. Use it to show how a loan is paid down or to read the balance after a given month. Each month's interest is the balance times the monthly rate, computed exactly and rounded half-up to cents, and the last payment absorbs the cent rounding so the balance ends at exactly zero. The schedule has at most 600 rows and ends early when cent rounding pays the loan off sooner, and inputs outside the schema bounds fail validation."""
        # Round the principal to cents and find the level payment.
        principal_cents = FinanceToolFunctions._half_up(Fraction(repr(principal)) * _CENTS_PER_UNIT)
        monthly_interest_fraction = Fraction(repr(annual_rate_percent)) / _MONTHLY_RATE_DIVISOR
        payment_cents = FinanceToolFunctions._half_up(FinanceToolFunctions._level_payment(principal_cents, monthly_interest_fraction, term_months))

        # Walk the months in whole cents and write every row as money.
        money = FinanceToolFunctions._money_text
        rows = FinanceToolFunctions._amortize(principal_cents, monthly_interest_fraction, term_months, payment_cents)
        schedule = [
            {"month": month, "payment": money(paid), "principal": money(repaid), "interest": money(interest), "balance": money(balance)}
            for month, paid, repaid, interest, balance in rows
        ]
        return {"monthly_payment": money(payment_cents), "schedule": schedule}

    @staticmethod
    def net_present_value(
        rate_percent: Annotated[float, Field(description="The discount rate per period in percent, not as a fraction of one. It must be above minus 100 and at most 1,000. Each flow is divided by one plus this rate raised to the flow's period number. A rate whose powers overflow or shrink to zero over the series fails with an error naming this parameter.", allow_inf_nan=False, gt=_LOWEST_RATE_PERCENT, le=PREBUILT_MAX_RATE_PERCENT)],
        cash_flows: Annotated[list[_FINITE_NUMBER], Field(description="The cash flows in period order, starting at period zero. Money paid out is negative and money received is positive. The list needs at least one flow and at most 10,000. Every flow must be a finite number.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Compute the net present value of a series of periodic cash flows at a discount rate given in percent. Use it to judge an investment or to compare projects whose flows arrive at regular intervals. The first flow is at period zero and is not discounted, which differs from the spreadsheet NPV function that discounts the first flow by one period. A rate whose powers overflow or shrink to zero over the series, or a result outside the floating-point range, fails with an error naming rate_percent."""
        # Build the discount factor of every period, refusing a rate
        # whose powers leave the floating-point range.
        growth = 1 + rate_percent / _PERCENT
        expected = "a rate whose powers stay within the floating-point range over the whole series"
        try:
            factors = [growth**period for period in range(len(cash_flows))]
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("rate_percent", "a power of one plus the rate overflows", expected) from exc
        if factors[-1] == 0:
            raise PrebuiltToolSupport.argument_error("rate_percent", "a power of one plus the rate shrinks to zero", expected)

        # Add the discounted flows with an exactly rounded sum.
        try:
            total = math.fsum(flow / factor for flow, factor in zip(cash_flows, factors, strict=True))
        except (OverflowError, ValueError) as exc:
            raise PrebuiltToolSupport.argument_error("rate_percent", "the discounted flows add up past the floating-point range", expected) from exc
        return {"npv": PrebuiltToolSupport.float_result(total, "rate_percent")}

    @staticmethod
    def internal_rate_of_return(
        cash_flows: Annotated[list[_FINITE_NUMBER], Field(description="The cash flows in period order, starting at period zero. Money paid out is negative and money received is positive. The list needs between 2 and 600 flows, with at least one of each sign. Every flow must be a finite number.", min_length=2, max_length=PREBUILT_MAX_CASH_FLOWS)],
    ) -> PrebuiltToolOutput:
        """Find the internal rate of return of a series of periodic cash flows, the discount rate in percent at which their net present value is zero. Use it to compare the yield of investments or loans whose flows arrive at regular intervals. The search scans rates from minus 99 percent to 1,000 percent in steps of one percent and bisects the first sign change it finds, so the result is within a billionth of a percentage point of that root. The flows need at least one positive and one negative amount, and flows whose value never changes sign in that range fail with an error naming cash_flows."""
        expected = "flows with at least one positive and one negative amount whose net present value changes sign between minus 99 and 1,000 percent"
        if not (any(flow > 0 for flow in cash_flows) and any(flow < 0 for flow in cash_flows)):
            raise PrebuiltToolSupport.argument_error("cash_flows", "the flows do not include both a positive and a negative amount", expected)

        # Scan the grid in order, skipping rates whose value cannot be
        # computed, until the value is zero or changes sign.
        npv = partial(FinanceToolFunctions._npv_at, cash_flows)
        previous: tuple[float, float] | None = None
        for step in range(PREBUILT_IRR_GRID_POINTS):
            guess = PREBUILT_IRR_GRID_START + step * PREBUILT_IRR_GRID_STEP
            value = npv(guess)
            if value is None:
                continue
            if value == 0:
                return {"irr_percent": guess * _PERCENT}
            if previous is not None and (value > 0) != (previous[1] > 0):
                # Bisect between the two grid points around the root.
                return {"irr_percent": FinanceToolFunctions._bisect_root(npv, previous[0], previous[1], guess) * _PERCENT}
            previous = (guess, value)
        raise PrebuiltToolSupport.argument_error("cash_flows", "the net present value never changes sign on the search grid", expected)

    @staticmethod
    def compound_annual_growth_rate(
        start_value: Annotated[float, Field(description="The value at the start of the period, which must be above zero. Any unit works as long as the end value uses the same one. Only the ratio of the two values matters. Zero or a negative start fails validation.", allow_inf_nan=False, gt=0)],
        end_value: Annotated[float, Field(description="The value at the end of the period, which must be zero or more. An end value of zero gives a rate of minus 100 percent. It must use the same unit as the start value. A negative end fails validation.", allow_inf_nan=False, ge=0)],
        years: Annotated[float, Field(description="The length of the period in years, above zero and at most 1,000. Fractional years are allowed. The rate is the steady yearly rate that compounds to the overall ratio over this time. Zero years fails validation.", allow_inf_nan=False, gt=0, le=PREBUILT_MAX_FINANCE_YEARS)],
    ) -> PrebuiltToolOutput:
        """Compute the compound annual growth rate in percent, the steady yearly rate that turns a start value into an end value over a number of years. Use it to express the growth of revenue, savings, or any other quantity as one yearly rate. The rate is the end value over the start value, raised to one over the years, minus one, times 100, and an end value of zero gives minus 100 percent. The start value and the years must be above zero, and a rate outside the floating-point range fails with an error naming years."""
        # Raise the ratio to one over the years; when the ratio itself
        # leaves the normal float range, work through logarithms.
        ratio = end_value / start_value
        try:
            if end_value == 0 or (math.isfinite(ratio) and ratio >= sys.float_info.min):
                growth = ratio ** (1 / years)
            else:
                growth = math.exp((math.log(end_value) - math.log(start_value)) / years)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("years", "the growth over one year is outside the floating-point range", "values and years whose yearly growth is a finite number") from exc
        return {"cagr_percent": PrebuiltToolSupport.float_result((growth - 1) * _PERCENT, "years")}

    @staticmethod
    def percentage_change(
        old_value: Annotated[float, Field(description="The earlier value the change is measured from. It may be negative, and the change divides by its absolute value. Zero fails with an error, because the change would be undefined. It must be a finite number.", allow_inf_nan=False)],
        new_value: Annotated[float, Field(description="The later value the change is measured to. It may be any finite number, including zero or a negative value. The difference is this value minus the old value. Both values must use the same unit.", allow_inf_nan=False)],
    ) -> PrebuiltToolOutput:
        """Compute the percentage change and the plain difference from an old value to a new value. Use it for growth, decline, or variance questions where the direction of the change matters. The change divides the difference by the absolute old value, so a drop from a negative old value is still reported as negative. An old value of zero fails with an error naming old_value, because the change is undefined."""
        if old_value == 0:
            raise PrebuiltToolSupport.argument_error("old_value", "it is zero, so the percentage change is undefined", "an old value other than zero")
        difference = PrebuiltToolSupport.float_result(new_value - old_value, "new_value")
        change = PrebuiltToolSupport.float_result(difference / abs(old_value) * _PERCENT, "old_value")
        return {"change_percent": change, "difference": difference}

    @staticmethod
    def percentage_breakdown(
        labels: Annotated[list[Annotated[str, Field(max_length=PREBUILT_MAX_SHORT_TEXT_CHARS)]], Field(description="The label of each value, in the same order as the values. Each label is repeated in its share entry and may hold at most ten thousand characters. The list needs at least one label and at most 10,000. Labels need not be unique.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        values: Annotated[list[_FINITE_NUMBER], Field(description="The amounts to turn into shares, one for each label and in the same order. Each value must be zero or more, and their sum must be above zero. Every value is read exactly from its shortest decimal text. A list whose length differs from labels fails with an error.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        decimal_places: Annotated[int, Field(description="How many decimal places each percent text has, from 0 to 10. Every share has exactly this many fractional digits, and zero places gives whole percents with no point. The default is 1. The shares always sum to exactly 100 at this precision.", ge=0, le=PREBUILT_MAX_SHARE_PLACES)] = 1,
    ) -> PrebuiltToolOutput:
        """Turn labelled values into percentage shares, written as texts that add up to exactly 100, along with the total and each value. Use it for charts, budget splits, or survey results where the rounded shares must still sum to 100. Each share is computed exactly, rounded down to the chosen decimal places, and the units of the last place still missing go one each to the largest remainders, ties to the earlier entry. Lists of different lengths, a negative value, or values that add up to zero fail with an error naming values."""
        # Pair labels with values and total the values exactly.
        pairs = PrebuiltToolSupport.paired_values(labels, values, "values")
        exact_total = PrebuiltToolSupport.weight_total(values, "values")
        try:
            total = math.fsum(values)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("values", "the values add up past the floating-point range", "values whose sum is a finite number") from exc

        # Share out 100 percent in units of the last decimal place.
        units = FinanceToolFunctions._largest_remainder(_PERCENT * 10**decimal_places, [Fraction(repr(value)) for value in values], exact_total)
        shares = [
            {"label": label, "value": value, "percent": FinanceToolFunctions._unit_text(count, decimal_places)}
            for (label, value), count in zip(pairs, units, strict=True)
        ]
        return {"total": total, "shares": shares}

    @staticmethod
    def allocate_amount(
        amount: Annotated[str, Field(description="The exact amount to split, written as plain decimal text with no exponent. It must be zero or more and must not be finer than the decimal places allow. The text may hold at most 4,002 characters. It is never converted to a binary float.", pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)],
        weights: Annotated[list[_FINITE_NUMBER], Field(description="The relative weight of each part, in the order the parts are returned. Each weight must be zero or more, and their sum must be above zero. Weights are read exactly from their shortest decimal text. The list needs at least one weight and at most 10,000.", min_length=1, max_length=PREBUILT_MAX_LIST_ITEMS)],
        decimal_places: Annotated[int, Field(description="How many decimal places each part has, from 0 to 10. Every part has exactly this many fractional digits, and zero places gives whole units with no point. The default is 2, which suits most currencies. The parts always add up to exactly the amount.", ge=0, le=PREBUILT_MAX_SHARE_PLACES)] = 2,
    ) -> PrebuiltToolOutput:
        """Split an exact decimal amount across weights so that the parts, written as texts, add up to exactly that amount. Use it to divide money or any other quantity fairly when the smallest unit cannot be split. Each part is computed exactly, rounded down to the chosen decimal places, and the units of the last place still missing go one each to the largest remainders, ties to the earlier weight. A negative amount or one finer than the decimal places fails naming amount, and a negative weight or weights that add up to zero fail naming weights."""
        # Express the amount in units of the last decimal place, which
        # must be a whole number of them.
        exact_amount = Fraction(PrebuiltToolSupport.parse_decimal_text(amount, "amount"))
        expected = f"an amount of zero or more with at most {decimal_places} fractional digits"
        if exact_amount < 0:
            raise PrebuiltToolSupport.argument_error("amount", "the amount is negative", expected)
        scaled = exact_amount * 10**decimal_places
        if scaled.denominator != 1:
            raise PrebuiltToolSupport.argument_error("amount", "the amount is finer than the decimal places allow", expected)

        # Share the units out by weight with the largest remainders.
        weight_sum = PrebuiltToolSupport.weight_total(weights, "weights")
        units = FinanceToolFunctions._largest_remainder(scaled.numerator, [Fraction(repr(weight)) for weight in weights], weight_sum)
        return {"allocations": [FinanceToolFunctions._unit_text(count, decimal_places) for count in units]}

    @staticmethod
    def split_tax_inclusive_amount(
        gross_amount: Annotated[str, Field(description="The tax-inclusive total, written as plain decimal text with no exponent. It must be zero or more, at most one quadrillion, and have at most two fractional digits. The text may hold at most 4,002 characters. It is never converted to a binary float.", pattern=PREBUILT_DECIMAL_TEXT_PATTERN, max_length=PREBUILT_MAX_DECIMAL_TEXT_CHARS)],
        tax_rate_percent: Annotated[float, Field(description="The tax rate in percent, not as a fraction of one, from zero to 1,000. The net amount is the gross divided by one plus this rate over 100. A rate of zero leaves the whole gross as net. The rate is read exactly from its shortest decimal text.", allow_inf_nan=False, ge=0, le=PREBUILT_MAX_RATE_PERCENT)],
    ) -> PrebuiltToolOutput:
        """Split a gross amount that already includes tax into its net amount and its tax amount, as money texts with two decimals. Use it for invoices and receipts where only the tax-inclusive total is known. The net amount is the gross divided by one plus the rate, computed exactly and rounded half-up to cents, and the tax is the gross minus the net, so the two always add up to the gross. A negative gross, one with more than two decimals, or one above one quadrillion fails with an error naming gross_amount."""
        # Read the gross in whole cents, refusing values that are not
        # whole cents or lie outside the money range.
        gross_cents = Fraction(PrebuiltToolSupport.parse_decimal_text(gross_amount, "gross_amount")) * _CENTS_PER_UNIT
        expected = "an amount from zero to one quadrillion with at most two fractional digits"
        if gross_cents < 0 or gross_cents > PREBUILT_MAX_MONEY_AMOUNT * _CENTS_PER_UNIT:
            raise PrebuiltToolSupport.argument_error("gross_amount", "the amount is outside the money range", expected)
        if gross_cents.denominator != 1:
            raise PrebuiltToolSupport.argument_error("gross_amount", "the amount has more than two fractional digits", expected)

        # Divide out the tax exactly and round the net to cents once.
        net_cents = FinanceToolFunctions._half_up(gross_cents / (1 + Fraction(repr(tax_rate_percent)) / _PERCENT))
        return {
            "net_amount": FinanceToolFunctions._money_text(net_cents),
            "tax_amount": FinanceToolFunctions._money_text(gross_cents.numerator - net_cents),
        }

    @staticmethod
    def _future_value(principal: float, annual_rate_percent: float, years: float, compounding: CompoundingFrequency) -> tuple[int, int]:
        """Return the cent-rounded principal and future value in whole cents, growing in the 50-digit context in the section 9.2 item 16 order."""
        with PrebuiltToolSupport.decimal_context(PREBUILT_FINANCE_PRECISION):
            start = Decimal(repr(principal)).quantize(_CENT, ROUND_HALF_UP)
            yearly_interest_fraction = Decimal(repr(annual_rate_percent)) / _PERCENT
            span = Decimal(repr(years))
            periods = _PERIODS_PER_YEAR.get(compounding)
            try:
                if periods is None:
                    grown = start * (yearly_interest_fraction * span).exp()
                else:
                    base = 1 + yearly_interest_fraction / periods
                    exponent = periods * span
                    grown = start * base**exponent
            except DecimalException as exc:
                raise PrebuiltToolSupport.argument_error("years", "the future value leaves the decimal range", "inputs whose future value is below 10^47") from exc
            # @intent prebuilt-finance-overflow-guard
            # Every value must stay within the 50-digit context, so a
            # future value of 10^47 or more fails before it is rounded.
            if grown >= _FUTURE_VALUE_CEILING:
                raise PrebuiltToolSupport.argument_error("years", "the future value is 10^47 or more", "inputs whose future value is below 10^47")
            final = grown.quantize(_CENT, ROUND_HALF_UP)
            return int(start.scaleb(_MONEY_PLACES)), int(final.scaleb(_MONEY_PLACES))

    @staticmethod
    def _level_payment(principal_cents: int, monthly_interest_fraction: Fraction, term_months: int) -> Fraction:
        """Return the exact level payment in cents: P*i / (1 - (1 + i)^-n), or P / n at a zero rate."""
        if monthly_interest_fraction == 0:
            return Fraction(principal_cents, term_months)
        return principal_cents * monthly_interest_fraction / (1 - (1 + monthly_interest_fraction) ** -term_months)

    @staticmethod
    def _amortize(principal_cents: int, monthly_interest_fraction: Fraction, term_months: int, payment_cents: int) -> list[tuple[int, int, int, int, int]]:
        """Walk a loan month by month in whole cents and return (month, payment, principal, interest, balance) rows up to a zero balance."""
        rows: list[tuple[int, int, int, int, int]] = []
        balance = principal_cents
        for month in range(1, term_months + 1):
            # The interest is rounded half-up to cents; the last month,
            # or a month that can clear the balance, pays it all off.
            interest = math.floor(balance * monthly_interest_fraction + _HALF)
            owed = balance + interest
            paid = owed if month == term_months or owed <= payment_cents else payment_cents
            balance -= paid - interest
            rows.append((month, paid, paid - interest, interest, balance))
            if balance == 0:
                break
        return rows

    @staticmethod
    def _half_up(value: Fraction) -> int:
        """Round an exact value to a whole number, half away from zero, which is ROUND_HALF_UP applied to the exact value."""
        rounded = math.floor(abs(value) + _HALF)
        return -rounded if value < 0 else rounded

    @staticmethod
    def _money_text(cents: int) -> str:
        """Write a whole number of cents as money text with exactly two fractional digits and no negative zero."""
        whole, part = divmod(abs(cents), _CENTS_PER_UNIT)
        sign = "-" if cents < 0 else ""
        return f"{sign}{whole}.{part:0{_MONEY_PLACES}d}"

    @staticmethod
    def _npv_at(cash_flows: Sequence[float], rate: float) -> float | None:
        """Return the net present value the rate search uses, or None when it raises or is not finite."""
        try:
            value = math.fsum(flow / (1 + rate) ** period for period, flow in enumerate(cash_flows))
        except (OverflowError, ZeroDivisionError, ValueError):
            return None
        return value if math.isfinite(value) else None

    @staticmethod
    def _bisect_root(npv: Callable[[float], float | None], low: float, low_value: float, high: float) -> float:
        """Bisect a sign change of npv between two rates until the bracket is within the tolerance or the step budget runs out."""
        for _ in range(PREBUILT_IRR_BISECTION_STEPS):
            if high - low <= PREBUILT_IRR_TOLERANCE:
                break
            middle = (low + high) / 2
            value = npv(middle)
            if value is None:
                expected = "flows whose net present value can be computed at every rate inside the bracket"
                raise PrebuiltToolSupport.argument_error("cash_flows", "the net present value could not be computed while narrowing the root", expected)
            if value == 0:
                return middle
            if (value > 0) == (low_value > 0):
                low, low_value = middle, value
            else:
                high = middle
        return (low + high) / 2

    @staticmethod
    def _largest_remainder(total_units: int, weights: Sequence[Fraction], weight_sum: Fraction) -> list[int]:
        """Share whole units by exact weight: round each share down, then give one more unit to the largest remainders, ties to the lower index."""
        exact = [total_units * weight / weight_sum for weight in weights]
        counts = [math.floor(share) for share in exact]
        missing = total_units - sum(counts)
        ranked = sorted(range(len(exact)), key=lambda index: (counts[index] - exact[index], index))
        for index in ranked[:missing]:
            counts[index] += 1
        return counts

    @staticmethod
    def _unit_text(units: int, places: int) -> str:
        """Write a count of last-place units as decimal text with exactly the given number of fractional digits."""
        if places == 0:
            return str(units)
        whole, part = divmod(units, 10**places)
        return f"{whole}.{part:0{places}d}"

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.compound_interest_future_value,
            cls.loan_payment_amount,
            cls.amortization_schedule,
            cls.net_present_value,
            cls.internal_rate_of_return,
            cls.compound_annual_growth_rate,
            cls.percentage_change,
            cls.percentage_breakdown,
            cls.allocate_amount,
            cls.split_tax_inclusive_amount,
        )


__all__ = ["FinanceToolFunctions"]
