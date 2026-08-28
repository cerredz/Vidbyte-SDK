"""Context Protocol Header

Description:
    Defines the AdversarialAgentDescriptor dataclass — a thin composition wrapper
    for YAML-loaded adversarial agent configurations. Includes a self-contained
    AdversarialSettings dataclass and nested AgentDescriptor objects for worker and
    adversary agents.
Purpose:
    Provides a typed configuration object that the YamlLoader produces from an
    adversarial-agent YAML document. Validates presence of both worker and adversary,
    distinct names, and validates reviewer budget/review settings.
Architecture:
    - AdversarialSettings: frozen dataclass with reviewer count, rounds, timeouts,
      and budget controls. Self-validating via __post_init__.
    - AdversarialAgentDescriptor: frozen dataclass composing AdversarialSettings and
      AgentDescriptor instances for worker and adversary.
    - __post_init__ validates identity, worker/adversary presence, and name uniqueness.
    - to_agent_kwargs() maps to AdversarialAgent.__init__ keyword arguments.
Relations:
    - Produced by vidbyte/lib/config/loader.py.
    - Composes AgentDescriptor from vidbyte/lib/dataclasses/agent_descriptor.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.agent_descriptor import AgentDescriptor

_MAX_NAME_CHARS = 256
_MAX_SYSTEM_PROMPT_CHARS = 500_000
_MAX_DESCRIPTION_CHARS = 2000


@dataclass(frozen=True, slots=True)
class AdversarialSettings:
    """Validated controls for one adversarial workflow. Composed by AdversarialAgentDescriptor."""

    num_adversaries: int = 1
    adversarial_rounds: int = 1
    min_successful_adversaries: int = 1
    per_adversary_timeout: float | None = None
    max_review_chars: int = 4000
    max_worker_output_chars: int = 12000
    specialties: tuple[str, ...] = ()
    fresh_adversaries_each_round: bool = False
    run_timeout_seconds: float | None = None
    max_child_calls: int | None = None

    def __post_init__(self) -> None:
        # Validates positive counts, threshold reachability, and specialty alignment.
        for field_name in ("num_adversaries", "adversarial_rounds", "min_successful_adversaries", "max_review_chars", "max_worker_output_chars"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value <= 0:
                raise ConfigurationError(
                    f"AdversarialSettings.{field_name} must be a positive integer.",
                    details={"field": field_name, "actual": value},
                )
        if self.min_successful_adversaries > self.num_adversaries:
            raise ConfigurationError(
                "AdversarialSettings.min_successful_adversaries cannot exceed num_adversaries.",
                details={"field": "min_successful_adversaries", "actual": self.min_successful_adversaries, "num_adversaries": self.num_adversaries},
            )
        if self.specialties and len(self.specialties) not in (1, self.num_adversaries):
            raise ConfigurationError(
                "AdversarialSettings.specialties must be empty, contain one shared lens, or align exactly with num_adversaries.",
                details={"field": "specialties", "actual_count": len(self.specialties), "num_adversaries": self.num_adversaries},
            )
        if self.per_adversary_timeout is not None and self.per_adversary_timeout <= 0:
            raise ConfigurationError(
                "AdversarialSettings.per_adversary_timeout must be positive when provided.",
                details={"field": "per_adversary_timeout", "actual": self.per_adversary_timeout},
            )
        if self.run_timeout_seconds is not None and self.run_timeout_seconds <= 0:
            raise ConfigurationError(
                "AdversarialSettings.run_timeout_seconds must be positive when provided.",
                details={"field": "run_timeout_seconds", "actual": self.run_timeout_seconds},
            )
        if self.max_child_calls is not None and self.max_child_calls <= 0:
            raise ConfigurationError(
                "AdversarialSettings.max_child_calls must be positive when provided.",
                details={"field": "max_child_calls", "actual": self.max_child_calls},
            )


@dataclass(frozen=True, slots=True)
class AdversarialAgentDescriptor:
    """Typed adversarial agent configuration loaded from a YAML document."""

    name: str = ""
    system_prompt: str = ""
    description: str = ""
    worker: "AgentDescriptor | None" = None
    adversary: "AgentDescriptor | None" = None
    settings: AdversarialSettings = field(default_factory=AdversarialSettings)
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates identity, worker and adversary presence, and distinct names.
        self._validate_identity()
        self._validate_worker()
        self._validate_adversary()

    def to_agent_kwargs(self, *, worker_instance: Any = None, adversary_instance: Any = None) -> dict[str, Any]:
        # Returns keyword arguments for AdversarialAgent.__init__ after the caller supplies live agent instances.
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "description": self.description,
            "worker": worker_instance,
            "adversary": adversary_instance,
            "settings": self.settings,
            "capabilities": self.capabilities,
            "metadata": dict(self.metadata),
        }

    def _validate_identity(self) -> None:
        # Validates name and system_prompt are non-empty and within length limits.
        if not self.name or not self.name.strip():
            raise ConfigurationError(
                "Adversarial agent name must be a non-empty string.",
                details={"field": "name", "expected": "non-empty string"},
            )
        if len(self.name) > _MAX_NAME_CHARS:
            raise ConfigurationError(
                f"Adversarial agent name must be at most {_MAX_NAME_CHARS} characters.",
                details={"field": "name", "max_chars": _MAX_NAME_CHARS, "actual_chars": len(self.name)},
            )
        if not self.system_prompt or not self.system_prompt.strip():
            raise ConfigurationError(
                "Adversarial agent system_prompt must be a non-empty string.",
                details={"field": "system_prompt", "expected": "non-empty string"},
            )
        if len(self.system_prompt) > _MAX_SYSTEM_PROMPT_CHARS:
            raise ConfigurationError(
                f"Adversarial agent system_prompt must be at most {_MAX_SYSTEM_PROMPT_CHARS} characters.",
                details={"field": "system_prompt", "max_chars": _MAX_SYSTEM_PROMPT_CHARS, "actual_chars": len(self.system_prompt)},
            )
        if len(self.description) > _MAX_DESCRIPTION_CHARS:
            raise ConfigurationError(
                f"Adversarial agent description must be at most {_MAX_DESCRIPTION_CHARS} characters.",
                details={"field": "description", "max_chars": _MAX_DESCRIPTION_CHARS, "actual_chars": len(self.description)},
            )

    def _validate_worker(self) -> None:
        # Validates the worker agent is present with non-empty name and system_prompt.
        if self.worker is None:
            raise ConfigurationError(
                "Adversarial agent must have a worker agent.",
                details={"field": "worker", "expected": "non-null AgentDescriptor"},
            )
        if not self.worker.name or not self.worker.name.strip():
            raise ConfigurationError(
                "Adversarial worker agent must have a non-empty name.",
                details={"field": "worker.name", "expected": "non-empty string"},
            )
        if not self.worker.system_prompt or not self.worker.system_prompt.strip():
            raise ConfigurationError(
                "Adversarial worker agent must have a non-empty system_prompt.",
                details={"field": "worker.system_prompt", "expected": "non-empty string"},
            )

    def _validate_adversary(self) -> None:
        # Validates the adversary agent is present and has a different name than the worker.
        if self.adversary is None:
            raise ConfigurationError(
                "Adversarial agent must have an adversary agent.",
                details={"field": "adversary", "expected": "non-null AgentDescriptor"},
            )
        if not self.adversary.name or not self.adversary.name.strip():
            raise ConfigurationError(
                "Adversarial adversary agent must have a non-empty name.",
                details={"field": "adversary.name", "expected": "non-empty string"},
            )
        if not self.adversary.system_prompt or not self.adversary.system_prompt.strip():
            raise ConfigurationError(
                "Adversarial adversary agent must have a non-empty system_prompt.",
                details={"field": "adversary.system_prompt", "expected": "non-empty string"},
            )
        if self.worker is not None and self.adversary.name == self.worker.name:
            raise ConfigurationError(
                "Adversarial worker and adversary agents must have different names.",
                details={
                    "field": "adversary.name",
                    "actual": self.adversary.name,
                    "worker_name": self.worker.name,
                },
            )


__all__ = ["AdversarialAgentDescriptor", "AdversarialSettings"]
