"""JSON exact and subset graders for structured-output evals."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from vidbyte.evals.base import BaseGrader
from vidbyte.evals.types import EvalCase, GraderResult


class JSONExactMatchGrader(BaseGrader):
    """Grader that compares parsed JSON values for exact equality."""

    name: ClassVar[str] = "json_exact_match"

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Parses actual and expected JSON-compatible values and compares them.
        actual_value, actual_error = self._parse_value(actual)
        expected_value, expected_error = self._parse_value(case.expected)
        if actual_error:
            return GraderResult(score=0.0, passed=False, reason=f"Output is not valid JSON: {actual_error}")
        if expected_error:
            return GraderResult(score=0.0, passed=False, reason=f"Expected value is not valid JSON: {expected_error}")
        passed = self._json_equal(actual_value, expected_value)
        score = 1.0 if passed else 0.0
        reason = "JSON matched exactly." if passed else "JSON did not match expected value."
        return GraderResult(score=score, passed=passed, reason=reason)

    def _parse_value(self, value: object) -> tuple[Any, str | None]:
        # Parses strings as JSON and accepts already structured JSON-compatible values.
        if isinstance(value, str):
            try:
                return json.loads(value), None
            except json.JSONDecodeError as exc:
                return None, str(exc)
        return value, None

    def _json_equal(self, actual: Any, expected: Any) -> bool:
        # @intent json-bool-is-not-number
        # JSON keeps booleans and numbers apart, but Python says True == 1, so a boolean only equals a boolean.
        # Integers and floats stay comparable because JSON has a single number type (1 == 1.0).
        if isinstance(actual, bool) or isinstance(expected, bool):
            return isinstance(actual, bool) and isinstance(expected, bool) and actual == expected
        if isinstance(actual, dict) and isinstance(expected, dict):
            return actual.keys() == expected.keys() and all(self._json_equal(actual[key], expected[key]) for key in expected)
        if isinstance(actual, list) and isinstance(expected, list):
            return len(actual) == len(expected) and all(self._json_equal(a, e) for a, e in zip(actual, expected, strict=True))
        return actual == expected


class JSONSubsetGrader(JSONExactMatchGrader):
    """Grader that checks whether expected JSON is contained within actual JSON."""

    name: ClassVar[str] = "json_subset"

    async def agrade(self, case: EvalCase, actual: str) -> GraderResult:
        # Parses JSON-compatible values and checks recursive containment.
        actual_value, actual_error = self._parse_value(actual)
        expected_value, expected_error = self._parse_value(case.expected)
        if actual_error:
            return GraderResult(score=0.0, passed=False, reason=f"Output is not valid JSON: {actual_error}")
        if expected_error:
            return GraderResult(score=0.0, passed=False, reason=f"Expected value is not valid JSON: {expected_error}")
        passed = self._contains_subset(actual_value, expected_value)
        score = 1.0 if passed else 0.0
        reason = "JSON contains expected subset." if passed else "JSON does not contain expected subset."
        return GraderResult(score=score, passed=passed, reason=reason)

    def _contains_subset(self, actual: Any, expected: Any) -> bool:
        # Recursively checks whether expected is contained inside actual.
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                return False
            return all(key in actual and self._contains_subset(actual[key], value) for key, value in expected.items())
        if isinstance(expected, list):
            if not isinstance(actual, list) or len(expected) > len(actual):
                return False
            return all(self._contains_subset(actual[index], value) for index, value in enumerate(expected))
        return self._json_equal(actual, expected)

