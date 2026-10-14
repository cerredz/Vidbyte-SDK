"""FILE: vidbyte/tools/builtins/prebuilt/unit_conversion.py

PURPOSE: Defines UnitConversionToolFunctions, the ten prebuilt tools that convert a value between units of length, mass, temperature, volume, area, speed, duration, energy, fuel economy, and data size.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the UNIT_CONVERSION category is chosen. Reads the exact factor tables in vidbyte/lib/constants/units.py and the unit enums in vidbyte/lib/enums/units.py, and raises through PrebuiltToolSupport in _support.py.
ARCHITECTURE NOTE: Every conversion follows D-13: the float input enters exact arithmetic through its shortest text, the factor strings are read as Fraction, the whole conversion is exact, and the result is turned into a float by one correctly rounded float() call. Scale conversions multiply by the source factor and divide by the target factor. Temperature is affine and goes through kelvin, and fuel economy goes through kilometers per liter, with liters per 100 kilometers as its inverse.
FUNCTION INVENTORY: convert_length, convert_mass, convert_temperature, convert_volume, convert_area, convert_speed, convert_duration, convert_energy, convert_fuel_economy, and convert_data_size are the tools; _scaled applies a factor table; _to_kelvin and _from_kelvin carry the temperature offsets; _to_kilometers_per_liter and _from_kilometers_per_liter carry the fuel economy factors; _result rounds once into the output; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new unit adds its enum member in vidbyte/lib/enums/units.py and its exact factor string in vidbyte/lib/constants/units.py; the tools here need no change. A new kind of quantity adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.8, and its entry in tool_functions.
WHAT NOT TO DO IN THIS FILE: 1. Do not multiply floats or store float factors; every factor is an exact string read as Fraction. 2. Do not build a Fraction from a float directly; use repr(x) so the value is its shortest decimal text. 3. Do not round more than once; the only rounding is the final float() call.
KNOWN EDGE CASES: Absolute zero itself is a valid temperature, and anything colder fails. Liters per 100 kilometers is inverse, so fuel economy values of zero or less fail. A huge value converted into a tiny unit can pass the float range and fails, while a tiny result may round to zero, which is finite and returned.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.8, section 9.2 unit factor tables and item 5, D-13); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_finance_units.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import Annotated, TypeVar

from pydantic import Field

from vidbyte.lib.constants.units import (
    AREA_UNIT_FACTORS,
    CELSIUS_KELVIN_OFFSET,
    DATA_SIZE_UNIT_FACTORS,
    DURATION_UNIT_FACTORS,
    ENERGY_UNIT_FACTORS,
    LENGTH_UNIT_FACTORS,
    MASS_UNIT_FACTORS,
    SPEED_UNIT_FACTORS,
    VOLUME_UNIT_FACTORS,
)
from vidbyte.lib.enums.units import (
    AreaUnit,
    DataSizeUnit,
    DurationUnit,
    EnergyUnit,
    FuelEconomyUnit,
    LengthUnit,
    MassUnit,
    SpeedUnit,
    TemperatureUnit,
    VolumeUnit,
)
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_UnitT = TypeVar("_UnitT", bound=Enum)

_KELVIN_OFFSET = Fraction(CELSIUS_KELVIN_OFFSET)
_FAHRENHEIT_FREEZING_POINT = 32
_FAHRENHEIT_DEGREES_PER_KELVIN = Fraction(9, 5)
_KILOMETERS_PER_MILE = Fraction(LENGTH_UNIT_FACTORS[LengthUnit.MILE]) / Fraction(LENGTH_UNIT_FACTORS[LengthUnit.KILOMETER])
_INVERSE_FUEL_DISTANCE = 100
_KILOMETERS_PER_LITER_FACTORS: MappingProxyType[FuelEconomyUnit, Fraction] = MappingProxyType(
    {
        FuelEconomyUnit.MILES_PER_US_GALLON: _KILOMETERS_PER_MILE / Fraction(VOLUME_UNIT_FACTORS[VolumeUnit.US_GALLON]),
        FuelEconomyUnit.MILES_PER_IMPERIAL_GALLON: _KILOMETERS_PER_MILE / Fraction(VOLUME_UNIT_FACTORS[VolumeUnit.IMPERIAL_GALLON]),
        FuelEconomyUnit.KILOMETERS_PER_LITER: Fraction(1),
    }
)

_VALUE_PARAMETER_DESCRIPTION = "The amount to convert, measured in from_unit. It may be negative or fractional, and it is read exactly from its shortest decimal text. The conversion multiplies exact unit factors and rounds only once, at the end. A result outside the floating-point range fails with an error naming this parameter."
_FROM_UNIT_PARAMETER_DESCRIPTION = "The unit the value is measured in, chosen from the listed unit names. Names are lowercase words joined by underscores. Every unit is defined exactly, so converting there and back returns the starting value up to float rounding. An unknown unit name fails validation."
_TO_UNIT_PARAMETER_DESCRIPTION = "The unit to convert the value into, chosen from the listed unit names. Names are lowercase words joined by underscores. The result repeats this unit name next to the converted value. An unknown unit name fails validation."


class UnitConversionToolFunctions:
    """The unit_conversion category: exact conversions between units of one physical quantity."""

    @staticmethod
    def convert_length(
        value: Annotated[float, Field(description=_VALUE_PARAMETER_DESCRIPTION, allow_inf_nan=False)],
        from_unit: Annotated[LengthUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[LengthUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert a length between metric and imperial units, from nanometers and millimeters to miles and nautical miles. Use it whenever a length, distance, or height must be expressed in another unit, because the factors are the exact international definitions. The math runs in exact fractions and rounds once to a float, and negative values are allowed because lengths can be signed offsets. A result outside the floating-point range fails with an error naming value."""
        exact = UnitConversionToolFunctions._scaled(value, LENGTH_UNIT_FACTORS, from_unit, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def convert_mass(
        value: Annotated[float, Field(description=_VALUE_PARAMETER_DESCRIPTION, allow_inf_nan=False)],
        from_unit: Annotated[MassUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[MassUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert a mass between metric and imperial units, from milligrams and grams to pounds, stone, and short and long tons. Use it for weights in recipes, shipping, or science where the target unit differs from the source. The factors are the exact international avoirdupois definitions, and the math runs in exact fractions that are rounded once to a float. A result outside the floating-point range fails with an error naming value."""
        exact = UnitConversionToolFunctions._scaled(value, MASS_UNIT_FACTORS, from_unit, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def convert_temperature(
        value: Annotated[float, Field(description="The temperature to convert, measured in from_unit. It may be negative, but it must not be colder than absolute zero in that unit. It is read exactly from its shortest decimal text, and the conversion runs through kelvin in exact arithmetic. A temperature below absolute zero fails with an error naming this parameter.", allow_inf_nan=False)],
        from_unit: Annotated[TemperatureUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[TemperatureUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert a temperature between Celsius, Fahrenheit, kelvin, and Rankine. Use it for weather, cooking, or science questions, where mental arithmetic with the offsets often slips. The conversion goes through kelvin in exact fractions, using the exact offset between Celsius and kelvin, and rounds once to a float. A temperature below absolute zero in its unit fails with an error naming value, while absolute zero itself is allowed."""
        # Move to kelvin, refuse anything colder than absolute zero, and
        # move from kelvin to the target scale.
        kelvin = UnitConversionToolFunctions._to_kelvin(Fraction(repr(value)), from_unit)
        if kelvin < 0:
            raise PrebuiltToolSupport.argument_error("value", "the temperature is below absolute zero", "a temperature at or above absolute zero in from_unit")
        exact = UnitConversionToolFunctions._from_kelvin(kelvin, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def convert_volume(
        value: Annotated[float, Field(description=_VALUE_PARAMETER_DESCRIPTION, allow_inf_nan=False)],
        from_unit: Annotated[VolumeUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[VolumeUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert a volume between metric, US customary, and imperial units, from milliliters and cubic meters to teaspoons, cups, pints, quarts, and gallons. Use it for recipes, fuel, and container sizes, and pick the US or the imperial unit on purpose because they differ. The factors are exact definitions, and the math runs in exact fractions that are rounded once to a float. A result outside the floating-point range fails with an error naming value."""
        exact = UnitConversionToolFunctions._scaled(value, VOLUME_UNIT_FACTORS, from_unit, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def convert_area(
        value: Annotated[float, Field(description=_VALUE_PARAMETER_DESCRIPTION, allow_inf_nan=False)],
        from_unit: Annotated[AreaUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[AreaUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert an area between metric and imperial units, from square millimeters to hectares, acres, and square miles. Use it for land, floor, and map areas that must be expressed in another unit system. The factors are the squares of exact length definitions, and the math runs in exact fractions that are rounded once to a float. A result outside the floating-point range fails with an error naming value."""
        exact = UnitConversionToolFunctions._scaled(value, AREA_UNIT_FACTORS, from_unit, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def convert_speed(
        value: Annotated[float, Field(description=_VALUE_PARAMETER_DESCRIPTION, allow_inf_nan=False)],
        from_unit: Annotated[SpeedUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[SpeedUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert a speed between meters per second, kilometers per hour, miles per hour, knots, and feet per second. Use it for travel, wind, and vehicle speeds given in a different unit. The factors are exact, with a knot being one nautical mile per hour, and the math runs in exact fractions that are rounded once to a float. A result outside the floating-point range fails with an error naming value."""
        exact = UnitConversionToolFunctions._scaled(value, SPEED_UNIT_FACTORS, from_unit, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def convert_duration(
        value: Annotated[float, Field(description=_VALUE_PARAMETER_DESCRIPTION, allow_inf_nan=False)],
        from_unit: Annotated[DurationUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[DurationUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert a duration between nanoseconds, microseconds, milliseconds, seconds, minutes, hours, days, and weeks. Use it for timing, scheduling, and performance figures given in a different unit. Months and years are left out because their length varies, a day is always 86,400 seconds, and the math runs in exact fractions that are rounded once to a float. A result outside the floating-point range fails with an error naming value."""
        exact = UnitConversionToolFunctions._scaled(value, DURATION_UNIT_FACTORS, from_unit, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def convert_energy(
        value: Annotated[float, Field(description=_VALUE_PARAMETER_DESCRIPTION, allow_inf_nan=False)],
        from_unit: Annotated[EnergyUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[EnergyUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert an amount of energy between joules, kilojoules, megajoules, calories, kilocalories, watt-hours, kilowatt-hours, British thermal units, and electronvolts. Use it for nutrition, electricity, heating, and physics questions that mix energy units. The calorie is the thermochemical calorie and the British thermal unit is the international table value, and the math runs in exact fractions that are rounded once to a float. A result outside the floating-point range fails with an error naming value."""
        exact = UnitConversionToolFunctions._scaled(value, ENERGY_UNIT_FACTORS, from_unit, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def convert_fuel_economy(
        value: Annotated[float, Field(description="The fuel economy to convert, measured in from_unit. It must be above zero, because liters per 100 kilometers is the inverse of the distance units and has no meaning at zero. It is read exactly from its shortest decimal text. A value of zero or less fails with an error naming this parameter.", allow_inf_nan=False)],
        from_unit: Annotated[FuelEconomyUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[FuelEconomyUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert fuel economy between miles per US gallon, miles per imperial gallon, kilometers per liter, and liters per 100 kilometers. Use it to compare vehicle efficiency figures quoted in different countries. The conversion goes through kilometers per liter in exact fractions, and liters per 100 kilometers is the inverse, so a higher value there means more fuel used. A value of zero or less fails with an error naming value, because the inverse unit has no meaning there."""
        # Refuse economy values the inverse unit cannot express, then go
        # through kilometers per liter.
        if value <= 0:
            raise PrebuiltToolSupport.argument_error("value", "the fuel economy is zero or negative", "a fuel economy above zero")
        kilometers_per_liter = UnitConversionToolFunctions._to_kilometers_per_liter(Fraction(repr(value)), from_unit)
        exact = UnitConversionToolFunctions._from_kilometers_per_liter(kilometers_per_liter, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def convert_data_size(
        value: Annotated[float, Field(description=_VALUE_PARAMETER_DESCRIPTION, allow_inf_nan=False)],
        from_unit: Annotated[DataSizeUnit, Field(description=_FROM_UNIT_PARAMETER_DESCRIPTION)],
        to_unit: Annotated[DataSizeUnit, Field(description=_TO_UNIT_PARAMETER_DESCRIPTION)],
    ) -> PrebuiltToolOutput:
        """Convert a data size between bits, bytes, decimal multiples such as kilobytes, and binary multiples such as kibibytes. Use it for storage, file, and bandwidth sizes, where decimal and binary prefixes are easy to mix up. Decimal prefixes are powers of 1,000, binary prefixes are powers of 1,024, and a bit is one eighth of a byte, and the math runs in exact fractions that are rounded once to a float. A result outside the floating-point range fails with an error naming value."""
        exact = UnitConversionToolFunctions._scaled(value, DATA_SIZE_UNIT_FACTORS, from_unit, to_unit)
        return UnitConversionToolFunctions._result(exact, to_unit)

    @staticmethod
    def _scaled(value: float, factors: Mapping[_UnitT, str], from_unit: _UnitT, to_unit: _UnitT) -> Fraction:
        """Convert exactly through the base unit: the value times the source factor over the target factor."""
        return Fraction(repr(value)) * Fraction(factors[from_unit]) / Fraction(factors[to_unit])

    @staticmethod
    def _to_kelvin(degrees: Fraction, unit: TemperatureUnit) -> Fraction:
        """Express an exact temperature in kelvin."""
        match unit:
            case TemperatureUnit.CELSIUS:
                return degrees + _KELVIN_OFFSET
            case TemperatureUnit.FAHRENHEIT:
                return (degrees - _FAHRENHEIT_FREEZING_POINT) / _FAHRENHEIT_DEGREES_PER_KELVIN + _KELVIN_OFFSET
            case TemperatureUnit.RANKINE:
                return degrees / _FAHRENHEIT_DEGREES_PER_KELVIN
            case _:
                return degrees

    @staticmethod
    def _from_kelvin(kelvin: Fraction, unit: TemperatureUnit) -> Fraction:
        """Express an exact kelvin temperature in another scale."""
        match unit:
            case TemperatureUnit.CELSIUS:
                return kelvin - _KELVIN_OFFSET
            case TemperatureUnit.FAHRENHEIT:
                return (kelvin - _KELVIN_OFFSET) * _FAHRENHEIT_DEGREES_PER_KELVIN + _FAHRENHEIT_FREEZING_POINT
            case TemperatureUnit.RANKINE:
                return kelvin * _FAHRENHEIT_DEGREES_PER_KELVIN
            case _:
                return kelvin

    @staticmethod
    def _to_kilometers_per_liter(economy: Fraction, unit: FuelEconomyUnit) -> Fraction:
        """Express an exact fuel economy in kilometers per liter, inverting liters per 100 kilometers."""
        if unit == FuelEconomyUnit.LITERS_PER_100_KILOMETERS:
            return _INVERSE_FUEL_DISTANCE / economy
        return economy * _KILOMETERS_PER_LITER_FACTORS[unit]

    @staticmethod
    def _from_kilometers_per_liter(kilometers_per_liter: Fraction, unit: FuelEconomyUnit) -> Fraction:
        """Express an exact kilometers-per-liter economy in another unit, inverting for liters per 100 kilometers."""
        if unit == FuelEconomyUnit.LITERS_PER_100_KILOMETERS:
            return _INVERSE_FUEL_DISTANCE / kilometers_per_liter
        return kilometers_per_liter / _KILOMETERS_PER_LITER_FACTORS[unit]

    @staticmethod
    def _result(exact: Fraction, to_unit: Enum) -> PrebuiltToolOutput:
        """Round the exact result once into a float and pair it with the target unit name."""
        try:
            converted = float(exact)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("value", "the converted value is outside the floating-point range", "a value whose converted result is a finite number") from exc
        return {"value": converted, "unit": to_unit.value}

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.convert_length,
            cls.convert_mass,
            cls.convert_temperature,
            cls.convert_volume,
            cls.convert_area,
            cls.convert_speed,
            cls.convert_duration,
            cls.convert_energy,
            cls.convert_fuel_economy,
            cls.convert_data_size,
        )


__all__ = ["UnitConversionToolFunctions"]
