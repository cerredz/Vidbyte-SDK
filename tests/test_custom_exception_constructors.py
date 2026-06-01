"""Context Protocol Header

Description:
    Unit tests for ProviderConfigurationError and ProviderResponseError custom exception constructors.
Purpose:
    Verifies decoupled signature implementation, domain parameter scoping, detail dictionary truncation/isolation, and subclass hierarchies.
Architecture:
    - CustomExceptionConstructorTests: unittest.TestCase suite.
Key Functions:
    - test_provider_configuration_error_instantiation: Verifies [Edge Case] base initialization.
    - test_provider_response_error_excerpt_truncation: Verifies [Edge Case] text truncation boundaries.
    - test_provider_configuration_error_parameter_constraints: Verifies [Hidden Failure] signature restrictions.
    - test_provider_response_error_details_isolation: Verifies [Silent Failure] object detail scoping.
    - test_subclass_structure_and_inheritance: Verifies [Hidden Assumption] exception hierarchy structure.
Relations:
    Validates custom constructors in vidbyte/lib/errors/base.py.
Similar Files:
    - tests/test_openrouter_provider.py
"""

from __future__ import annotations

import unittest

from vidbyte.lib.errors import (
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    VidbyteSdkError,
)


class CustomExceptionConstructorTests(unittest.TestCase):
    """Test suite verifying design constraints for custom exception constructors."""

    def test_provider_configuration_error_instantiation(self) -> None:
        # Verifies that ProviderConfigurationError constructs cleanly with only required provider metadata.
        err = ProviderConfigurationError("Configuration failed", provider="openai")
        self.assertEqual(err.message, "Configuration failed")
        self.assertEqual(err.provider, "openai")
        self.assertEqual(err.details, {"provider": "openai"})

    def test_provider_response_error_excerpt_truncation(self) -> None:
        # Verifies that response body excerpts exceeding 500 characters are correctly truncated in safe details.
        long_excerpt = "x" * 600
        err = ProviderResponseError("Response normalization failed", provider="gemini", status_code=200, response_excerpt=long_excerpt)
        self.assertEqual(err.provider, "gemini")
        self.assertEqual(err.status_code, 200)
        self.assertEqual(err.response_excerpt, long_excerpt)
        self.assertEqual(len(err.details["response_excerpt"]), 500)
        self.assertEqual(err.details["response_excerpt"], "x" * 500)

    def test_provider_configuration_error_parameter_constraints(self) -> None:
        # Verifies that ProviderConfigurationError rejects HTTP request-specific arguments during initialization.
        with self.assertRaises(TypeError):
            # type: ignore[call-arg]
            ProviderConfigurationError("Config error", provider="anthropic", status_code=500)  # type: ignore[call-arg]

    def test_provider_response_error_details_isolation(self) -> None:
        # Verifies that details metadata dictionary mutations are fully isolated between distinct exception instances.
        err1 = ProviderResponseError("Err1", provider="openai", status_code=400)
        err2 = ProviderResponseError("Err2", provider="xai", status_code=500)
        err1.details["mutated"] = True
        self.assertNotIn("mutated", err2.details)

    def test_subclass_structure_and_inheritance(self) -> None:
        # Verifies that configuration and response exceptions inherit directly from VidbyteSdkError instead of ProviderRequestError.
        self.assertTrue(issubclass(ProviderConfigurationError, VidbyteSdkError))
        self.assertFalse(issubclass(ProviderConfigurationError, ProviderRequestError))
        self.assertTrue(issubclass(ProviderResponseError, VidbyteSdkError))
        self.assertFalse(issubclass(ProviderResponseError, ProviderRequestError))
