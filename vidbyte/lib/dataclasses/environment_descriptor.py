"""Context Protocol Header

Description:
    Defines the EnvironmentDescriptor dataclass for YAML-loaded environment/pipeline configurations.
Purpose:
    Provides a typed object for multi-stage paradigm pipeline configs loaded from YAML.
    Each stage (context, splitter, adversarial, implementation) holds an AgentDescriptor.
    Pipeline-wide settings use the existing ContextMinimalFanoutSettings class.
Architecture:
    - EnvironmentDescriptor: frozen dataclass holding per-stage agent descriptors and
      a settings object. Validates that at least one stage is defined.
Relations:
    - Produced by vidbyte/lib/config/loader.py.
    - Composes AgentDescriptor and ContextMinimalFanoutSettings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.agent_descriptor import AgentDescriptor
    from vidbyte.paradigms.context_minimal_fanout.types import ContextMinimalFanoutSettings


@dataclass(frozen=True, slots=True)
class EnvironmentDescriptor:
    """Typed environment/pipeline configuration loaded from a YAML document."""

    name: str = ""
    context: "AgentDescriptor | None" = None
    splitter: "AgentDescriptor | None" = None
    adversarial: "AgentDescriptor | None" = None
    implementation: "AgentDescriptor | None" = None
    settings: "ContextMinimalFanoutSettings | None" = None

    def __post_init__(self) -> None:
        # Validates that at least one stage agent is defined.
        if not self.name or not self.name.strip():
            raise ConfigurationError(
                "Environment name must be a non-empty string.",
                details={"field": "name", "expected": "non-empty string"},
            )
        if len(self.name) > 128:
            raise ConfigurationError(
                "Environment name must be at most 128 characters.",
                details={"field": "name", "max_chars": 128, "actual_chars": len(self.name)},
            )
        stages = (self.context, self.splitter, self.adversarial, self.implementation)
        if all(stage is None for stage in stages):
            raise ConfigurationError(
                "Environment must define at least one stage agent (context, splitter, adversarial, or implementation).",
                details={"field": "stages", "expected": "at least one non-null stage"},
            )


__all__ = ["EnvironmentDescriptor"]
