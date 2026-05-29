"""Context Protocol Header

Description:
    Verification script for Custom Exception Constructors.
Purpose:
    Runs all design doc test cases (unit tests) and outputs structured PASS/FAIL outcomes.
Architecture:
    Standalone runnable Python script directly importing and testing custom exception classes.
Key Functions:
    - main: Runs the verification suite and checks each rule boundary.
Relations:
    Related to docs/design/custom-exception-constructors.md and tests/test_custom_exception_constructors.py.
Similar Files:
    - None.
"""

from __future__ import annotations

import sys
from typing import Any

from vidbyte.lib.errors import (
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    VidbyteSdkError,
)


def main() -> None:
    # Executes the testing plan for custom exception constructors and prints the PASS/FAIL results.
    print("Running Custom Exception Constructors Verification...")
    tests = [
        ("ProviderConfigurationError with custom details [Edge Case]", test_config_error_instantiation),
        ("ProviderResponseError response excerpt truncation [Edge Case]", test_response_excerpt_truncation),
        ("Constructor parameter constraints [Hidden Failure]", test_parameter_constraints),
        ("Detail dictionary isolation [Silent Failure]", test_details_isolation),
        ("Subclass structure and inheritance [Hidden Assumption]", test_inheritance),
    ]

    passed = 0
    for name, test_func in tests:
        try:
            test_func()
            print(f"PASS: {name}")
            passed += 1
        except Exception as exc:
            print(f"FAIL: {name} (Error: {exc})")

    print(f"\nSummary: {passed}/{len(tests)} tests passed.")
    if passed < len(tests):
        sys.exit(1)
    sys.exit(0)


def test_config_error_instantiation() -> None:
    # Verifies that ProviderConfigurationError instantiates with provider and sets base details.
    err = ProviderConfigurationError("Missing API key", provider="anthropic")
    assert err.message == "Missing API key"
    assert err.provider == "anthropic"
    assert err.details == {"provider": "anthropic"}


def test_response_excerpt_truncation() -> None:
    # Verifies that ProviderResponseError truncates the response excerpt in details to 500 characters.
    long_excerpt = "a" * 600
    err = ProviderResponseError("Invalid JSON", provider="openai", status_code=500, response_excerpt=long_excerpt)
    assert err.provider == "openai"
    assert err.status_code == 500
    assert err.response_excerpt == long_excerpt
    assert len(err.details["response_excerpt"]) == 500
    assert err.details["response_excerpt"] == "a" * 500


def test_parameter_constraints() -> None:
    # Verifies that ProviderConfigurationError does not accept status_code or response_excerpt parameters.
    try:
        # type: ignore[call-arg]
        ProviderConfigurationError("Config failed", provider="openai", status_code=400)  # type: ignore[call-arg]
        raise AssertionError("TypeError not raised")
    except TypeError:
        pass


def test_details_isolation() -> None:
    # Verifies that detail dictionary mutations do not affect separate exception instances.
    err1 = ProviderResponseError("E1", provider="gemini", status_code=200)
    err2 = ProviderResponseError("E2", provider="openai", status_code=404)
    err1.details["custom_key"] = "test"
    assert "custom_key" not in err2.details


def test_inheritance() -> None:
    # Verifies that custom exception subclasses inherit from VidbyteSdkError instead of ProviderRequestError.
    assert issubclass(ProviderConfigurationError, VidbyteSdkError)
    assert not issubclass(ProviderConfigurationError, ProviderRequestError)
    assert issubclass(ProviderResponseError, VidbyteSdkError)
    assert not issubclass(ProviderResponseError, ProviderRequestError)


if __name__ == "__main__":
    main()
