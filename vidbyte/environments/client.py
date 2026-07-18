"""Context Protocol Header

Description:
    Defines EnvironmentsClient, the public namespace client for the
    environments package.
Purpose:
    Gives VidbyteSDK a single discoverable entry point for environment
    registries, rollout runners, and verifier audits.
Architecture:
    - EnvironmentsClient: Thin factory surface over registry, runner, and audit.
Relations:
    Instantiated by vidbyte.client.VidbyteSDK; wraps vidbyte.environments
    registry, runner, and audit modules.
Similar Files:
    - vidbyte/harnesses/client.py: Equivalent namespace client for harnesses.
"""

from __future__ import annotations

from typing import Any

from vidbyte.environments.audit import EnvironmentAudit
from vidbyte.environments.base import Environment
from vidbyte.environments.registry import EnvironmentRegistry
from vidbyte.environments.runner import EnvironmentRunner


class EnvironmentsClient:
    """Namespace client for environment registry access, rollouts, and audits."""

    def registry(self) -> type[EnvironmentRegistry]:
        """Return the environment registry class."""
        return EnvironmentRegistry

    def runner(self, environment: Environment, **kwargs: Any) -> EnvironmentRunner:
        """Build an EnvironmentRunner for an environment instance."""
        return EnvironmentRunner(environment, **kwargs)

    def audit(self, environment: Environment, **kwargs: Any) -> EnvironmentAudit:
        """Build an EnvironmentAudit for an environment instance."""
        return EnvironmentAudit(environment, **kwargs)


__all__ = [
    "EnvironmentsClient",
]
