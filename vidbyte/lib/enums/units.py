"""FILE: vidbyte/lib/enums/units.py

PURPOSE: Defines the ten unit vocabularies the prebuilt unit-conversion and geometry tools accept: length, mass, temperature, volume, area, speed, duration, energy, fuel economy, and data size.
ROLE IN CODEBASE: Imported by vidbyte/lib/constants/units.py, which keys each exact factor table by these members, and by vidbyte/tools/builtins/prebuilt/unit_conversion.py and geometry.py, whose tool signatures take them. Re-exported from vidbyte/lib/enums/__init__.py.
ARCHITECTURE NOTE: Units are a general vocabulary rather than a prebuilt-only one, so they live in their own domain module. Each value is the snake_case unit name the model sends.
FUNCTION INVENTORY: No functions; ten str Enum classes.
COMMON MODIFICATION PATTERNS: A new unit adds its member here and its exact factor to the matching table in vidbyte/lib/constants/units.py in the same change.
WHAT NOT TO DO IN THIS FILE: 1. Do not put conversion factors here; they belong in vidbyte/lib/constants/units.py. 2. Do not reorder members; the tests pin declaration order.
KNOWN EDGE CASES: Temperature and fuel economy are not plain factor scales, so their conversions are written in the tool rather than in a factor table.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (section 9.2 unit tables)
TESTS: tests/features/prebuilt_tools/ (test_prebuilt_toolset_contract.py and test_prebuilt_rows_finance_units.py)
"""

from __future__ import annotations

from enum import Enum


class LengthUnit(str, Enum):
    """Units of length."""

    NANOMETER = "nanometer"
    MICROMETER = "micrometer"
    MILLIMETER = "millimeter"
    CENTIMETER = "centimeter"
    METER = "meter"
    KILOMETER = "kilometer"
    INCH = "inch"
    FOOT = "foot"
    YARD = "yard"
    MILE = "mile"
    NAUTICAL_MILE = "nautical_mile"


class MassUnit(str, Enum):
    """Units of mass."""

    MILLIGRAM = "milligram"
    GRAM = "gram"
    KILOGRAM = "kilogram"
    METRIC_TON = "metric_ton"
    OUNCE = "ounce"
    POUND = "pound"
    STONE = "stone"
    SHORT_TON = "short_ton"
    LONG_TON = "long_ton"


class TemperatureUnit(str, Enum):
    """Units of temperature."""

    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"
    KELVIN = "kelvin"
    RANKINE = "rankine"


class VolumeUnit(str, Enum):
    """Units of volume, with US and imperial measures kept apart."""

    MILLILITER = "milliliter"
    LITER = "liter"
    CUBIC_CENTIMETER = "cubic_centimeter"
    CUBIC_METER = "cubic_meter"
    CUBIC_INCH = "cubic_inch"
    CUBIC_FOOT = "cubic_foot"
    US_TEASPOON = "us_teaspoon"
    US_TABLESPOON = "us_tablespoon"
    US_FLUID_OUNCE = "us_fluid_ounce"
    US_CUP = "us_cup"
    US_PINT = "us_pint"
    US_QUART = "us_quart"
    US_GALLON = "us_gallon"
    IMPERIAL_FLUID_OUNCE = "imperial_fluid_ounce"
    IMPERIAL_PINT = "imperial_pint"
    IMPERIAL_QUART = "imperial_quart"
    IMPERIAL_GALLON = "imperial_gallon"


class AreaUnit(str, Enum):
    """Units of area."""

    SQUARE_MILLIMETER = "square_millimeter"
    SQUARE_CENTIMETER = "square_centimeter"
    SQUARE_METER = "square_meter"
    SQUARE_KILOMETER = "square_kilometer"
    HECTARE = "hectare"
    SQUARE_INCH = "square_inch"
    SQUARE_FOOT = "square_foot"
    SQUARE_YARD = "square_yard"
    ACRE = "acre"
    SQUARE_MILE = "square_mile"


class SpeedUnit(str, Enum):
    """Units of speed."""

    METERS_PER_SECOND = "meters_per_second"
    KILOMETERS_PER_HOUR = "kilometers_per_hour"
    MILES_PER_HOUR = "miles_per_hour"
    KNOTS = "knots"
    FEET_PER_SECOND = "feet_per_second"


class DurationUnit(str, Enum):
    """Fixed-length units of time."""

    NANOSECOND = "nanosecond"
    MICROSECOND = "microsecond"
    MILLISECOND = "millisecond"
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"


class EnergyUnit(str, Enum):
    """Units of energy."""

    JOULE = "joule"
    KILOJOULE = "kilojoule"
    MEGAJOULE = "megajoule"
    CALORIE = "calorie"
    KILOCALORIE = "kilocalorie"
    WATT_HOUR = "watt_hour"
    KILOWATT_HOUR = "kilowatt_hour"
    BRITISH_THERMAL_UNIT = "british_thermal_unit"
    ELECTRONVOLT = "electronvolt"


class FuelEconomyUnit(str, Enum):
    """Units of fuel economy, including the inverse liters per 100 kilometers."""

    MILES_PER_US_GALLON = "miles_per_us_gallon"
    MILES_PER_IMPERIAL_GALLON = "miles_per_imperial_gallon"
    KILOMETERS_PER_LITER = "kilometers_per_liter"
    LITERS_PER_100_KILOMETERS = "liters_per_100_kilometers"


class DataSizeUnit(str, Enum):
    """Units of digital data size, decimal and binary."""

    BIT = "bit"
    BYTE = "byte"
    KILOBYTE = "kilobyte"
    MEGABYTE = "megabyte"
    GIGABYTE = "gigabyte"
    TERABYTE = "terabyte"
    PETABYTE = "petabyte"
    KIBIBYTE = "kibibyte"
    MEBIBYTE = "mebibyte"
    GIBIBYTE = "gibibyte"
    TEBIBYTE = "tebibyte"
    PEBIBYTE = "pebibyte"
    KILOBIT = "kilobit"
    MEGABIT = "megabit"
    GIGABIT = "gigabit"


__all__ = [
    "AreaUnit",
    "DataSizeUnit",
    "DurationUnit",
    "EnergyUnit",
    "FuelEconomyUnit",
    "LengthUnit",
    "MassUnit",
    "SpeedUnit",
    "TemperatureUnit",
    "VolumeUnit",
]
