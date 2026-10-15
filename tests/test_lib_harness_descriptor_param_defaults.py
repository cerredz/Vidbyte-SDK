"""FILE: tests/test_lib_harness_descriptor_param_defaults.py

PURPOSE:
    Regression tests for HarnessDescriptor param defaults: a list param refuses a
    default whose elements do not match the element type its declared type names,
    the same way a scalar param refuses a default of the wrong type, while every
    matching list default (including the empty list) is still accepted.

ROLE IN CODEBASE:
    Exercises HarnessDescriptor._validate_params and
    HarnessDescriptor._default_matches_type in
    vidbyte/lib/dataclasses/harness_descriptor.py through the dataclass constructor.

ARCHITECTURE NOTE:
    Each test builds a HarnessDescriptor directly with one param, so the real
    __post_init__ validation runs. No YAML, no files, no model calls.

COMMON MODIFICATION PATTERNS:
    Add a case here when _VALID_PARAM_TYPES gains a new list element type.

KNOWN EDGE CASES:
    A bool is an int in Python, so list[int] and list[float] must refuse True and
    False elements just as the scalar int and float types do; list[float] still
    accepts int elements, as scalar float does.

RELATED DOCS:
    vidbyte/lib/config/loader.py builds a HarnessDescriptor from a harness YAML
    document, so these rules apply to every loaded harness.

TESTS:
    python -m pytest tests/test_lib_harness_descriptor_param_defaults.py -q
"""

from __future__ import annotations

import unittest
from typing import Any

from vidbyte.lib.dataclasses.harness_descriptor import HarnessDescriptor
from vidbyte.lib.errors import ConfigurationError


def _build(param_type: str, default: Any) -> HarnessDescriptor:
    return HarnessDescriptor(
        name="probe",
        description="A harness used to check param defaults.",
        params={"value": {"type": param_type, "default": default}},
    )


class HarnessListParamDefaultTests(unittest.TestCase):
    def test_list_int_refuses_string_elements(self) -> None:
        with self.assertRaises(ConfigurationError):
            _build("list[int]", ["a"])

    def test_list_int_refuses_bool_elements(self) -> None:
        with self.assertRaises(ConfigurationError):
            _build("list[int]", [True])

    def test_list_str_refuses_int_elements(self) -> None:
        with self.assertRaises(ConfigurationError):
            _build("list[str]", [1])

    def test_list_float_refuses_string_elements(self) -> None:
        with self.assertRaises(ConfigurationError):
            _build("list[float]", ["x"])

    def test_matching_list_defaults_are_accepted(self) -> None:
        cases = [
            ("list[int]", [1, 2]),
            ("list[float]", [1, 2.5]),
            ("list[str]", ["a"]),
            ("list[int]", []),
            ("list[str]", []),
            ("list[float]", []),
        ]
        for param_type, default in cases:
            with self.subTest(param_type=param_type, default=default):
                descriptor = _build(param_type, default)
                self.assertEqual(descriptor.params["value"]["default"], default)


if __name__ == "__main__":
    unittest.main()
