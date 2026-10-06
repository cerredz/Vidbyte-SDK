"""FILE: vidbyte/agents/jev/decision_failures.py

PURPOSE: Distinguishes managed gateway access/configuration failures from Jev's advisory service failures.
ROLE IN CODEBASE: The Jev preflight gate, tool selector, and done-check decision boundary use one shared fail-closed policy.
ARCHITECTURE NOTE: This agent-layer policy reads typed SDK errors and DecisionModelConfig without changing provider behavior.
COMMON MODIFICATION PATTERNS: Update status classification with the product gateway contract and tests before changing callers.
KNOWN EDGE CASES: Missing managed credentials carry a specific error_kind; local request validation and transient outages remain advisory.
RELATED DOCS: docs/design/jev-managed-gateway-credentials.md and skills/jev-agent/SKILL.md.
TESTS: tests/test_jev_managed_gateway.py and scripts/test-jev-managed-gateway.py.
"""

from __future__ import annotations

from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    VIDBYTE_MANAGED_ACCESS_DENIAL_STATUS_CODES,
    VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND,
)
from vidbyte.lib.enums import DecisionModelMode
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderRequestError,
    VidbyteSdkError,
)


class JevDecisionFailurePolicy:
    """Keeps managed authorization failures distinct from advisory service failures."""

    @staticmethod
    def should_fail_closed(error: VidbyteSdkError, config: DecisionModelConfig) -> bool:
        # Stops a managed Jev path on missing credentials or explicit gateway access denial.
        # @intent only-managed-access-denials-stop-jev
        # Transient failures and local request/response problems remain advisory to preserve Jev's resilience.
        if config.mode is not DecisionModelMode.VIDBYTE_MANAGED:
            return False
        if isinstance(error, ProviderConfigurationError):
            return True
        if isinstance(error, ConfigurationError):
            return error.details.get("error_kind") == VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND
        return isinstance(error, ProviderRequestError) and error.status_code in VIDBYTE_MANAGED_ACCESS_DENIAL_STATUS_CODES


__all__ = ["JevDecisionFailurePolicy"]
