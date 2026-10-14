"""FILE: vidbyte/tools/builtins/prebuilt/geometry.py

PURPOSE: Defines GeometryToolFunctions, the seven prebuilt geometry tools: great-circle distance, initial bearing, destination point, reading and writing degrees-minutes-seconds coordinates, and the area and point-in-polygon tests of a flat polygon.
ROLE IN CODEBASE: Re-exported by vidbyte/tools/builtins/prebuilt/__init__.py and wrapped in FunctionTool objects by PrebuiltTools in vidbyte/tools/toolsets/prebuilt.py when the GEOMETRY category is chosen. Builds on PrebuiltToolSupport in _support.py for paired coordinate lists, finite results, and the argument error, and on the length factors in vidbyte/lib/constants/units.py.
ARCHITECTURE NOTE: The spherical tools use the classic haversine, bearing, and destination formulas in floating point on a sphere of radius PREBUILT_EARTH_RADIUS_KILOMETERS, converting units through the exact length factors. The polygon tools read every coordinate exactly from its shortest text as a Fraction, so collinear points and points on an edge are decided without rounding error, and decimal_degrees_to_dms rounds once in Decimal under the spec's float rounding rule.
FUNCTION INVENTORY: haversine_distance, initial_bearing, destination_point, dms_to_decimal_degrees, decimal_degrees_to_dms, polygon_area, and point_in_polygon are the tools; _kilometers_per_unit reads a length factor, _dms_parts parses degrees-minutes-seconds text, _exact_vertices pairs and converts polygon coordinates, and _ray_cast runs the even-odd test; tool_functions lists the tools in catalogue order.
COMMON MODIFICATION PATTERNS: A new geometry tool adds a static method with a 4 to 5 sentence description, its row in the spec's Appendix A.26, and its entry in tool_functions. A new distance unit is a LengthUnit member plus its factor in vidbyte/lib/constants/units.py, with no change here.
WHAT NOT TO DO IN THIS FILE: 1. Do not round degrees-minutes-seconds with round() or float arithmetic; convert once with Decimal(repr(x)), quantize the total, and split it afterwards. 2. Do not decide polygon orientation or boundary contact with float arithmetic; the exact Fraction test is what makes a zero area and an on-edge point reliable. 3. Do not hard-code a unit factor; read LENGTH_UNIT_FACTORS.
KNOWN EDGE CASES: Identical points give a distance of zero and a bearing of zero pointing north. A bearing just below a full turn can round to 360 in floating point, so the bearing is folded back into [0, 360). Huge polygon coordinates are exact as Fractions, so only the final conversion to float can overflow, and that fails with an error naming x. A value that rounds to zero seconds is written with the N or E hemisphere even when it was negative.
RELATED DOCS: docs/spec/prebuilt-agent-tools/spec.md (Appendix A.26, section 9.2 items 5, 13, 16, and 17, and the length factor table); vidbyte/tools/builtins/prebuilt/README.md
TESTS: tests/features/prebuilt_tools/test_prebuilt_rows_geometry_bits_markdown.py and the catalogue-wide tests in tests/features/prebuilt_tools/
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction
from typing import Annotated

from pydantic import Field

from vidbyte.lib.constants.prebuilt_tools import (
    PREBUILT_EARTH_RADIUS_KILOMETERS,
    PREBUILT_FINANCE_PRECISION,
    PREBUILT_MAX_LIST_ITEMS,
    PREBUILT_MAX_PHRASE_CHARS,
    PREBUILT_MAX_SIZE_DECIMAL_PLACES,
)
from vidbyte.lib.constants.units import LENGTH_UNIT_FACTORS
from vidbyte.lib.enums.prebuilt_tools import (
    CompassPoint,
    CoordinateAxis,
    PolygonOrientation,
)
from vidbyte.lib.enums.units import LengthUnit
from vidbyte.tools.builtins.prebuilt._support import (
    PrebuiltToolFunction,
    PrebuiltToolOutput,
    PrebuiltToolSupport,
)

_MAX_LATITUDE = 90
_MAX_LONGITUDE = 180
_FULL_TURN_DEGREES = 360
_MIN_POLYGON_VERTICES = 3
_HALF_TURN_DEGREES = 180
_COMPASS_POINTS = tuple(CompassPoint)
_COMPASS_SECTOR_DEGREES = _FULL_TURN_DEGREES / len(_COMPASS_POINTS)
_METERS_PER_KILOMETER = 1000
_SECONDS_PER_MINUTE = 60
_SECONDS_PER_DEGREE = 3600
_SOUTHERN_OR_WESTERN = ("S", "W")
_DMS_NUMBER = r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
_DMS_TEXT = re.compile(
    r"\s*(?P<lead>[NSEW])?\s*(?P<sign>[+-])?\s*"
    + rf"(?P<degrees>{_DMS_NUMBER})"
    + rf"(?:(?:\s*[°d:]\s*|\s+)(?P<minutes>{_DMS_NUMBER})"
    + rf"(?:(?:\s*['m′:]\s*|\s+)(?P<seconds>{_DMS_NUMBER})(?:\s*[\"s″])?|\s*['m′])?"
    + r"|\s*[°d])?"
    + r"\s*(?P<trail>[NSEW])?\s*"
)
_DMS_EXPECTED = "degrees with optional minutes and seconds, an optional sign or one N, S, E, or W hemisphere letter, minutes and seconds below 60, and a latitude of at most 90 or a longitude of at most 180"

_LATITUDE_PARAMETER_DESCRIPTION = "The latitude of the point in decimal degrees, positive north of the equator and negative south of it. It must be a finite number between -90 and 90. Values outside that range fail validation. Convert degrees-minutes-seconds text with dms_to_decimal_degrees first."
_LONGITUDE_PARAMETER_DESCRIPTION = "The longitude of the point in decimal degrees, positive east of the prime meridian and negative west of it. It must be a finite number between -180 and 180. Values outside that range fail validation. Convert degrees-minutes-seconds text with dms_to_decimal_degrees first."
_UNIT_PARAMETER_DESCRIPTION = "The length unit for the distance, chosen from metric, imperial, and nautical units. Units convert through exact factors to meters. The default is kilometer. The Earth radius behind the result is always the mean radius in kilometers."
_POLYGON_X_PARAMETER_DESCRIPTION = "The x coordinates of the polygon's vertices, in order around the polygon. Each value is a finite number on a flat plane, never a latitude or longitude on the sphere. The list needs at least three values and at most ten thousand. The polygon closes on its own, so repeating the first vertex at the end is optional."
_POLYGON_Y_PARAMETER_DESCRIPTION = "The y coordinates of the polygon's vertices, in the same order as the x coordinates. Each value is a finite number on a flat plane. The list needs at least three values and at most ten thousand. It must have exactly as many values as the x list, or the call fails with an error naming this parameter."

_LATITUDE = Annotated[float, Field(description=_LATITUDE_PARAMETER_DESCRIPTION, ge=-_MAX_LATITUDE, le=_MAX_LATITUDE, allow_inf_nan=False)]
_LONGITUDE = Annotated[float, Field(description=_LONGITUDE_PARAMETER_DESCRIPTION, ge=-_MAX_LONGITUDE, le=_MAX_LONGITUDE, allow_inf_nan=False)]
_COORDINATES = list[Annotated[float, Field(allow_inf_nan=False)]]


class GeometryToolFunctions:
    """The geometry category: great-circle navigation, coordinate notation, and flat polygons."""

    @staticmethod
    def haversine_distance(
        latitude1: _LATITUDE,
        longitude1: _LONGITUDE,
        latitude2: _LATITUDE,
        longitude2: _LONGITUDE,
        unit: Annotated[LengthUnit, Field(description=_UNIT_PARAMETER_DESCRIPTION)] = LengthUnit.KILOMETER,
    ) -> PrebuiltToolOutput:
        """Compute the great-circle distance between two points given by latitude and longitude, in the chosen length unit. Use it for straight-line travel distances between places on Earth, which a model cannot estimate reliably. The Earth is treated as a sphere with the mean radius, so the result can differ from an ellipsoid survey by up to about half a percent. Identical points give zero, and coordinates outside their ranges fail validation."""
        # Apply the haversine formula in radians; the square root is
        # held at one so rounding never pushes asin out of its domain.
        phi1, phi2 = math.radians(latitude1), math.radians(latitude2)
        half_lat = math.radians(latitude2 - latitude1) / 2
        half_lon = math.radians(longitude2 - longitude1) / 2
        haversine = math.sin(half_lat) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(half_lon) ** 2
        kilometers = 2 * PREBUILT_EARTH_RADIUS_KILOMETERS * math.asin(min(1.0, math.sqrt(haversine)))

        # Convert the kilometers into the chosen unit.
        distance = kilometers / float(GeometryToolFunctions._kilometers_per_unit(unit))
        return {"distance": distance, "unit": unit.value}

    @staticmethod
    def initial_bearing(latitude1: _LATITUDE, longitude1: _LONGITUDE, latitude2: _LATITUDE, longitude2: _LONGITUDE) -> PrebuiltToolOutput:
        """Compute the initial compass bearing for travelling along a great circle from the first point toward the second. Use it to say in which direction one place lies from another. The bearing is in degrees clockwise from true north, at least 0 and below 360, and the bearing changes along the way on a long route. It also returns the nearest of the 16 compass points, and identical points give a bearing of zero and north."""
        # Apply the forward azimuth formula in radians.
        phi1, phi2 = math.radians(latitude1), math.radians(latitude2)
        delta_lon = math.radians(longitude2 - longitude1)
        east = math.sin(delta_lon) * math.cos(phi2)
        north = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lon)
        is_same_point = latitude1 == latitude2 and longitude1 == longitude2
        angle = 0.0 if is_same_point else math.degrees(math.atan2(east, north))

        # Fold the angle into [0, 360), then pick the 16-point sector
        # centred on it.
        bearing = (angle + _FULL_TURN_DEGREES) % _FULL_TURN_DEGREES
        sector = int((bearing + _COMPASS_SECTOR_DEGREES / 2) // _COMPASS_SECTOR_DEGREES) % len(_COMPASS_POINTS)
        return {"bearing_degrees": bearing, "compass_point": _COMPASS_POINTS[sector].value}

    @staticmethod
    def destination_point(
        latitude: Annotated[float, Field(description="The latitude of the starting point in decimal degrees, positive north of the equator and negative south of it. It must be a finite number between -90 and 90. Values outside that range fail validation. Convert degrees-minutes-seconds text with dms_to_decimal_degrees first.", ge=-_MAX_LATITUDE, le=_MAX_LATITUDE, allow_inf_nan=False)],
        longitude: Annotated[float, Field(description="The longitude of the starting point in decimal degrees, positive east of the prime meridian and negative west of it. It must be a finite number between -180 and 180. Values outside that range fail validation. Convert degrees-minutes-seconds text with dms_to_decimal_degrees first.", ge=-_MAX_LONGITUDE, le=_MAX_LONGITUDE, allow_inf_nan=False)],
        bearing_degrees: Annotated[float, Field(description="The initial direction of travel in degrees clockwise from true north. Zero points north and ninety points east. It must be a finite number between 0 and 360. The route follows a great circle, so the direction changes along the way.", ge=0, le=_FULL_TURN_DEGREES, allow_inf_nan=False)],
        distance: Annotated[float, Field(description="How far to travel from the starting point, measured in the chosen unit. It must be a finite number of zero or more. Zero returns the starting point itself. A distance longer than the Earth's circumference wraps around the globe.", ge=0, allow_inf_nan=False)],
        unit: Annotated[LengthUnit, Field(description=_UNIT_PARAMETER_DESCRIPTION)] = LengthUnit.KILOMETER,
    ) -> PrebuiltToolOutput:
        """Compute the point reached by travelling a distance along a great circle from a starting point on an initial bearing. Use it to project a position forward, such as where a ship ends up after a known course and distance. The Earth is treated as a sphere with the mean radius, and the longitude of the result is normalized to at least -180 and below 180. A distance too large to convert into kilometers as a finite number fails with an error naming distance."""
        # Turn the distance into an angle at the centre of the Earth.
        kilometers = PrebuiltToolSupport.float_result(distance * float(GeometryToolFunctions._kilometers_per_unit(unit)), "distance")
        angle = kilometers / PREBUILT_EARTH_RADIUS_KILOMETERS
        phi1, lambda1, theta = math.radians(latitude), math.radians(longitude), math.radians(bearing_degrees)

        # Find the new latitude, held inside asin's domain against
        # rounding, and then the change in longitude.
        sin_phi2 = math.sin(phi1) * math.cos(angle) + math.cos(phi1) * math.sin(angle) * math.cos(theta)
        sin_phi2 = max(-1.0, min(1.0, sin_phi2))
        lambda2 = lambda1 + math.atan2(math.sin(theta) * math.sin(angle) * math.cos(phi1), math.cos(angle) - math.sin(phi1) * sin_phi2)

        # Normalize the longitude into [-180, 180).
        result_longitude = (math.degrees(lambda2) + _FULL_TURN_DEGREES + _HALF_TURN_DEGREES) % _FULL_TURN_DEGREES - _HALF_TURN_DEGREES
        return {"latitude": math.degrees(math.asin(sin_phi2)), "longitude": result_longitude}

    @staticmethod
    def dms_to_decimal_degrees(
        dms: Annotated[str, Field(description="The coordinate written as degrees, optional minutes, and optional seconds, each a plain or decimal number. The parts may be separated by spaces, colons, the degree, minute, and second symbols or their prime forms, or the letters d, m, and s. A sign or one uppercase hemisphere letter N, S, E, or W at the start or the end gives the direction. The text may hold at most two hundred characters.", min_length=1, max_length=PREBUILT_MAX_PHRASE_CHARS)],
    ) -> PrebuiltToolOutput:
        """Convert a coordinate written in degrees, minutes, and seconds into signed decimal degrees, with the axis its hemisphere letter implies. Use it before passing a written coordinate to the distance, bearing, or destination tools, which take decimal degrees. South and west, or a leading minus sign, give a negative value, and the axis is latitude for N or S, longitude for E or W, and null without a letter. Minutes or seconds of 60 or more, a sign together with S or W, a value past its axis range, or unreadable text fail with an error naming dms."""
        # Read the hemisphere letter, the sign, and the exact size of
        # the angle.
        hemisphere, sign, magnitude = GeometryToolFunctions._dms_parts(dms)
        if sign is not None and hemisphere in _SOUTHERN_OR_WESTERN:
            raise PrebuiltToolSupport.argument_error("dms", "the text has both a sign and an S or W hemisphere letter", _DMS_EXPECTED)

        # The hemisphere letter decides the axis and its range; without
        # one, only the wider longitude range is checked.
        axis = None if hemisphere is None else CoordinateAxis.LATITUDE if hemisphere in ("N", "S") else CoordinateAxis.LONGITUDE
        bound = _MAX_LATITUDE if axis is CoordinateAxis.LATITUDE else _MAX_LONGITUDE
        if magnitude > bound:
            raise PrebuiltToolSupport.argument_error("dms", f"the angle is more than {bound} degrees", _DMS_EXPECTED)

        # South, west, and a minus sign make the value negative.
        negative = sign == "-" or hemisphere in _SOUTHERN_OR_WESTERN
        return {"decimal_degrees": float(-magnitude if negative else magnitude), "axis": None if axis is None else axis.value}

    @staticmethod
    def decimal_degrees_to_dms(
        decimal_degrees: Annotated[float, Field(description="The coordinate in signed decimal degrees, where a negative value lies south or west. It must be a finite number. A latitude must be between -90 and 90, and a longitude between -180 and 180. A value outside its axis range fails with an error naming this parameter.", allow_inf_nan=False)],
        axis: Annotated[CoordinateAxis, Field(description="Whether the value is a latitude or a longitude. A latitude is written with N or S, and a longitude with E or W. The axis also sets the allowed range of the value. There is no default.")],
        seconds_decimal_places: Annotated[int, Field(description="How many fractional digits to keep in the seconds. The whole value is rounded half-even to this many places of an arc-second before it is split into parts. Zero writes whole seconds with no decimal point. The value must be between 0 and 6, and the default is 1.", ge=0, le=PREBUILT_MAX_SIZE_DECIMAL_PLACES)] = 1,
    ) -> PrebuiltToolOutput:
        """Write signed decimal degrees as whole degrees, whole minutes, and seconds with a hemisphere letter, both as text and as separate numbers. Use it to present a coordinate in the familiar notation of maps and charts. The value is rounded once, in exact decimal arithmetic, to the requested places of an arc-second and only then split, so no part ever reaches 60. A negative value that rounds to zero is written with N or E, and a value outside its axis range fails with an error naming decimal_degrees."""
        # Check the value against the range of its axis.
        bound = _MAX_LATITUDE if axis is CoordinateAxis.LATITUDE else _MAX_LONGITUDE
        if abs(decimal_degrees) > bound:
            raise PrebuiltToolSupport.argument_error("decimal_degrees", f"the value is outside the {axis.value} range", f"a {axis.value} from -{bound} to {bound} degrees")

        # Round the whole angle once, in arc-seconds, exactly from the
        # value's shortest text, and split it into parts afterwards.
        with PrebuiltToolSupport.decimal_context(PREBUILT_FINANCE_PRECISION):
            total = (abs(Decimal(repr(decimal_degrees))) * _SECONDS_PER_DEGREE).quantize(Decimal(1).scaleb(-seconds_decimal_places))
            degrees, remainder = divmod(total, _SECONDS_PER_DEGREE)
            minutes, seconds = divmod(remainder, _SECONDS_PER_MINUTE)
            seconds_text = f"{seconds:.{seconds_decimal_places}f}"

        # Pick the hemisphere and write the parts without zero padding.
        letters = ("S", "N") if axis is CoordinateAxis.LATITUDE else ("W", "E")
        hemisphere = letters[0] if decimal_degrees < 0 and total != 0 else letters[1]
        return {
            "dms": f"{int(degrees)}°{int(minutes)}′{seconds_text}″{hemisphere}",
            "degrees": int(degrees),
            "minutes": int(minutes),
            "seconds": float(seconds),
            "hemisphere": hemisphere,
        }

    @staticmethod
    def polygon_area(
        x: Annotated[_COORDINATES, Field(description=_POLYGON_X_PARAMETER_DESCRIPTION, min_length=_MIN_POLYGON_VERTICES, max_length=PREBUILT_MAX_LIST_ITEMS)],
        y: Annotated[_COORDINATES, Field(description=_POLYGON_Y_PARAMETER_DESCRIPTION, min_length=_MIN_POLYGON_VERTICES, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Compute the area, signed area, winding orientation, and perimeter of a flat polygon from its vertex coordinates. Use it for floor plans, plots on a grid, or any planar shape, but not for latitude and longitude, because it ignores the Earth's curvature. The signed area is positive for counterclockwise vertices and negative for clockwise ones, an exactly zero area is degenerate, and a self-intersecting polygon gives the net shoelace area. Lists of different lengths fail with an error naming y, and a result too large for a float fails with an error naming x."""
        # Pair the coordinates and read each exactly, then walk every
        # edge, including the one that closes the polygon.
        vertices = GeometryToolFunctions._exact_vertices(x, y, "y")
        edges = list(zip(vertices, vertices[1:] + vertices[:1], strict=True))

        # The shoelace sum gives twice the signed area exactly.
        doubled = sum((x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in edges), Fraction(0))

        # Convert to floats once at the end, refusing an overflow.
        try:
            signed_area = float(doubled / 2)
            perimeter = math.fsum(math.hypot(float(x2 - x1), float(y2 - y1)) for (x1, y1), (x2, y2) in edges)
        except OverflowError as exc:
            raise PrebuiltToolSupport.argument_error("x", "the area or perimeter is outside the floating-point range", "coordinates whose area and perimeter are finite numbers") from exc
        perimeter = PrebuiltToolSupport.float_result(perimeter, "x")

        # The sign of the exact sum gives the winding direction.
        orientation = PolygonOrientation.COUNTERCLOCKWISE if doubled > 0 else PolygonOrientation.CLOCKWISE if doubled < 0 else PolygonOrientation.DEGENERATE
        return {"area": abs(signed_area), "signed_area": signed_area, "orientation": orientation.value, "perimeter": perimeter}

    @staticmethod
    def point_in_polygon(
        point_x: Annotated[float, Field(description="The x coordinate of the point to test, on the same flat plane as the polygon. It must be a finite number. It is read exactly from its shortest decimal text. A point exactly on an edge counts as inside.", allow_inf_nan=False)],
        point_y: Annotated[float, Field(description="The y coordinate of the point to test, on the same flat plane as the polygon. It must be a finite number. It is read exactly from its shortest decimal text. A point exactly on an edge counts as inside.", allow_inf_nan=False)],
        polygon_x: Annotated[_COORDINATES, Field(description=_POLYGON_X_PARAMETER_DESCRIPTION, min_length=_MIN_POLYGON_VERTICES, max_length=PREBUILT_MAX_LIST_ITEMS)],
        polygon_y: Annotated[_COORDINATES, Field(description="The y coordinates of the polygon's vertices, in the same order as the x coordinates. Each value is a finite number on a flat plane. The list needs at least three values and at most ten thousand. It must have exactly as many values as polygon_x, or the call fails with an error naming this parameter.", min_length=_MIN_POLYGON_VERTICES, max_length=PREBUILT_MAX_LIST_ITEMS)],
    ) -> PrebuiltToolOutput:
        """Tell whether a point lies inside a flat polygon and whether it lies exactly on the polygon's boundary. Use it for hit tests on floor plans, grid maps, or any planar shape, but not for latitude and longitude on the globe. It applies the even-odd ray casting rule, so holes formed by a self-intersecting outline count as outside. A point on an edge or a vertex, found by an exact cross-product test, is on the boundary and counts as inside, and lists of different lengths fail with an error naming polygon_y."""
        # Read the polygon and the point exactly, then cast a ray.
        vertices = GeometryToolFunctions._exact_vertices(polygon_x, polygon_y, "polygon_y")
        inside, on_boundary = GeometryToolFunctions._ray_cast(Fraction(repr(point_x)), Fraction(repr(point_y)), vertices)
        return {"inside": inside or on_boundary, "on_boundary": on_boundary}

    @staticmethod
    def _kilometers_per_unit(unit: LengthUnit) -> Fraction:
        """Return the exact length of one unit in kilometers."""
        return Fraction(LENGTH_UNIT_FACTORS[unit]) / _METERS_PER_KILOMETER

    @staticmethod
    def _dms_parts(text: str) -> tuple[str | None, str | None, Fraction]:
        """Parse degrees-minutes-seconds text into its hemisphere letter, its sign, and the exact size of the angle in degrees."""
        match = _DMS_TEXT.fullmatch(text)
        if match is None:
            raise PrebuiltToolSupport.argument_error("dms", "the text is not a readable degrees, minutes, and seconds coordinate", _DMS_EXPECTED)
        if match["lead"] is not None and match["trail"] is not None:
            raise PrebuiltToolSupport.argument_error("dms", "the text has a hemisphere letter at both ends", _DMS_EXPECTED)
        minutes = Fraction(match["minutes"] or 0)
        seconds = Fraction(match["seconds"] or 0)
        if minutes >= _SECONDS_PER_MINUTE or seconds >= _SECONDS_PER_MINUTE:
            raise PrebuiltToolSupport.argument_error("dms", "the minutes or seconds are 60 or more", _DMS_EXPECTED)
        magnitude = Fraction(match["degrees"]) + minutes / _SECONDS_PER_MINUTE + seconds / _SECONDS_PER_DEGREE
        return match["lead"] or match["trail"], match["sign"], magnitude

    @staticmethod
    def _exact_vertices(xs: Sequence[float], ys: Sequence[float], second_name: str) -> list[tuple[Fraction, Fraction]]:
        """Pair two coordinate lists and read every value exactly from its shortest text."""
        return [(Fraction(repr(vertex_x)), Fraction(repr(vertex_y))) for vertex_x, vertex_y in PrebuiltToolSupport.paired_values(xs, ys, second_name)]

    @staticmethod
    def _ray_cast(point_x: Fraction, point_y: Fraction, vertices: Sequence[tuple[Fraction, Fraction]]) -> tuple[bool, bool]:
        """Run the exact even-odd test, returning whether the point is inside and whether it is on the boundary."""
        inside = False
        for (x1, y1), (x2, y2) in zip(vertices, [*vertices[1:], vertices[0]], strict=True):
            # A zero cross product inside the edge's bounding box puts
            # the point on the edge itself.
            cross = (x2 - x1) * (point_y - y1) - (y2 - y1) * (point_x - x1)
            if cross == 0 and min(x1, x2) <= point_x <= max(x1, x2) and min(y1, y2) <= point_y <= max(y1, y2):
                return True, True
            # Count the edges that a ray running right from the point
            # crosses; the half-open rule skips horizontal edges and
            # counts a shared end only once.
            if (y1 > point_y) != (y2 > point_y) and point_x < x1 + (point_y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        return inside, False

    @classmethod
    def tool_functions(cls) -> tuple[PrebuiltToolFunction, ...]:
        """Return the category's tool functions in catalogue order."""
        return (
            cls.haversine_distance,
            cls.initial_bearing,
            cls.destination_point,
            cls.dms_to_decimal_degrees,
            cls.decimal_degrees_to_dms,
            cls.polygon_area,
            cls.point_in_polygon,
        )


__all__ = ["GeometryToolFunctions"]
