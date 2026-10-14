"""FILE: vidbyte/lib/constants/units.py

PURPOSE: Holds the exact unit factor tables the prebuilt unit-conversion and geometry tools use: the size of one unit in its base unit for length, mass, volume, area, speed, duration, energy, and data size, plus the Celsius-to-Kelvin offset.
ROLE IN CODEBASE: Imported by vidbyte/tools/builtins/prebuilt/unit_conversion.py (every convert_* tool) and vidbyte/tools/builtins/prebuilt/geometry.py (distance units). Keyed by the unit enums in vidbyte/lib/enums/units.py.
ARCHITECTURE NOTE: Each factor is a decimal or ratio string that fractions.Fraction parses exactly, so a conversion multiplies exact fractions and rounds once when it turns the result into a float. The tables are read-only MappingProxyType views. Temperature is affine and fuel economy reuses the mile and gallon factors, so neither has a factor table of its own.
FUNCTION INVENTORY: No functions; eight factor tables and CELSIUS_KELVIN_OFFSET.
COMMON MODIFICATION PATTERNS: A new unit adds its enum member in vidbyte/lib/enums/units.py and its exact factor here in the same change. Write factors as exact decimal text or as a ratio, never as a float literal.
WHAT NOT TO DO IN THIS FILE: 1. Do not store float factors; a float such as 0.0254 is not exact. 2. Do not add conversion logic; it belongs in the tool module. 3. Do not import anything above vidbyte.lib.
KNOWN EDGE CASES: The electronvolt factor uses exponent notation, which Fraction parses exactly. Bits are one eighth of a byte, so the data size table holds a ratio.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (section 9.2 unit factor tables, D-13)
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_finance_units.py
"""

from __future__ import annotations

from types import MappingProxyType

from vidbyte.lib.enums.units import (
    AreaUnit,
    DataSizeUnit,
    DurationUnit,
    EnergyUnit,
    LengthUnit,
    MassUnit,
    SpeedUnit,
    VolumeUnit,
)

LENGTH_UNIT_FACTORS: MappingProxyType[LengthUnit, str] = MappingProxyType(
    {
        LengthUnit.NANOMETER: "0.000000001",
        LengthUnit.MICROMETER: "0.000001",
        LengthUnit.MILLIMETER: "0.001",
        LengthUnit.CENTIMETER: "0.01",
        LengthUnit.METER: "1",
        LengthUnit.KILOMETER: "1000",
        LengthUnit.INCH: "0.0254",
        LengthUnit.FOOT: "0.3048",
        LengthUnit.YARD: "0.9144",
        LengthUnit.MILE: "1609.344",
        LengthUnit.NAUTICAL_MILE: "1852",
    }
)

MASS_UNIT_FACTORS: MappingProxyType[MassUnit, str] = MappingProxyType(
    {
        MassUnit.MILLIGRAM: "0.000001",
        MassUnit.GRAM: "0.001",
        MassUnit.KILOGRAM: "1",
        MassUnit.METRIC_TON: "1000",
        MassUnit.OUNCE: "0.028349523125",
        MassUnit.POUND: "0.45359237",
        MassUnit.STONE: "6.35029318",
        MassUnit.SHORT_TON: "907.18474",
        MassUnit.LONG_TON: "1016.0469088",
    }
)

VOLUME_UNIT_FACTORS: MappingProxyType[VolumeUnit, str] = MappingProxyType(
    {
        VolumeUnit.MILLILITER: "0.001",
        VolumeUnit.LITER: "1",
        VolumeUnit.CUBIC_CENTIMETER: "0.001",
        VolumeUnit.CUBIC_METER: "1000",
        VolumeUnit.CUBIC_INCH: "0.016387064",
        VolumeUnit.CUBIC_FOOT: "28.316846592",
        VolumeUnit.US_TEASPOON: "0.00492892159375",
        VolumeUnit.US_TABLESPOON: "0.01478676478125",
        VolumeUnit.US_FLUID_OUNCE: "0.0295735295625",
        VolumeUnit.US_CUP: "0.2365882365",
        VolumeUnit.US_PINT: "0.473176473",
        VolumeUnit.US_QUART: "0.946352946",
        VolumeUnit.US_GALLON: "3.785411784",
        VolumeUnit.IMPERIAL_FLUID_OUNCE: "0.0284130625",
        VolumeUnit.IMPERIAL_PINT: "0.56826125",
        VolumeUnit.IMPERIAL_QUART: "1.1365225",
        VolumeUnit.IMPERIAL_GALLON: "4.54609",
    }
)

AREA_UNIT_FACTORS: MappingProxyType[AreaUnit, str] = MappingProxyType(
    {
        AreaUnit.SQUARE_MILLIMETER: "0.000001",
        AreaUnit.SQUARE_CENTIMETER: "0.0001",
        AreaUnit.SQUARE_METER: "1",
        AreaUnit.SQUARE_KILOMETER: "1000000",
        AreaUnit.HECTARE: "10000",
        AreaUnit.SQUARE_INCH: "0.00064516",
        AreaUnit.SQUARE_FOOT: "0.09290304",
        AreaUnit.SQUARE_YARD: "0.83612736",
        AreaUnit.ACRE: "4046.8564224",
        AreaUnit.SQUARE_MILE: "2589988.110336",
    }
)

SPEED_UNIT_FACTORS: MappingProxyType[SpeedUnit, str] = MappingProxyType(
    {
        SpeedUnit.METERS_PER_SECOND: "1",
        SpeedUnit.KILOMETERS_PER_HOUR: "5/18",
        SpeedUnit.MILES_PER_HOUR: "0.44704",
        SpeedUnit.KNOTS: "463/900",
        SpeedUnit.FEET_PER_SECOND: "0.3048",
    }
)

DURATION_UNIT_FACTORS: MappingProxyType[DurationUnit, str] = MappingProxyType(
    {
        DurationUnit.NANOSECOND: "1/1000000000",
        DurationUnit.MICROSECOND: "1/1000000",
        DurationUnit.MILLISECOND: "1/1000",
        DurationUnit.SECOND: "1",
        DurationUnit.MINUTE: "60",
        DurationUnit.HOUR: "3600",
        DurationUnit.DAY: "86400",
        DurationUnit.WEEK: "604800",
    }
)

ENERGY_UNIT_FACTORS: MappingProxyType[EnergyUnit, str] = MappingProxyType(
    {
        EnergyUnit.JOULE: "1",
        EnergyUnit.KILOJOULE: "1000",
        EnergyUnit.MEGAJOULE: "1000000",
        EnergyUnit.CALORIE: "4.184",
        EnergyUnit.KILOCALORIE: "4184",
        EnergyUnit.WATT_HOUR: "3600",
        EnergyUnit.KILOWATT_HOUR: "3600000",
        EnergyUnit.BRITISH_THERMAL_UNIT: "1055.05585262",
        EnergyUnit.ELECTRONVOLT: "1.602176634e-19",
    }
)

DATA_SIZE_UNIT_FACTORS: MappingProxyType[DataSizeUnit, str] = MappingProxyType(
    {
        DataSizeUnit.BIT: "1/8",
        DataSizeUnit.BYTE: "1",
        DataSizeUnit.KILOBYTE: "1000",
        DataSizeUnit.MEGABYTE: "1000000",
        DataSizeUnit.GIGABYTE: "1000000000",
        DataSizeUnit.TERABYTE: "1000000000000",
        DataSizeUnit.PETABYTE: "1000000000000000",
        DataSizeUnit.KIBIBYTE: "1024",
        DataSizeUnit.MEBIBYTE: "1048576",
        DataSizeUnit.GIBIBYTE: "1073741824",
        DataSizeUnit.TEBIBYTE: "1099511627776",
        DataSizeUnit.PEBIBYTE: "1125899906842624",
        DataSizeUnit.KILOBIT: "125",
        DataSizeUnit.MEGABIT: "125000",
        DataSizeUnit.GIGABIT: "125000000",
    }
)

CELSIUS_KELVIN_OFFSET = "273.15"

__all__ = [
    "AREA_UNIT_FACTORS",
    "CELSIUS_KELVIN_OFFSET",
    "DATA_SIZE_UNIT_FACTORS",
    "DURATION_UNIT_FACTORS",
    "ENERGY_UNIT_FACTORS",
    "LENGTH_UNIT_FACTORS",
    "MASS_UNIT_FACTORS",
    "SPEED_UNIT_FACTORS",
    "VOLUME_UNIT_FACTORS",
]
