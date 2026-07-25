"""Context Protocol Header

Description:
    Defines the AggregateAgentDescriptor dataclass — a thin composition wrapper for
    YAML-loaded aggregate (mixture-of-agents) configurations. Composes the existing
    ProposerSpec and AggregateConfig classes.
Purpose:
    Provides a typed configuration object that the YamlLoader produces from an
    aggregate-agent YAML document. Validates proposer presence, label uniqueness,
    and config bounds.
Architecture:
    - AggregateAgentDescriptor: frozen dataclass composing ProposerSpec and
      AggregateConfig.
    - __post_init__ validates proposers list, label uniqueness, and config invariants.
    - to_agent_kwargs() maps to AggregateAgent.__init__ keyword arguments.
Relations:
    - Produced by vidbyte/lib/config/loader.py.
    - Composes ProposerSpec and AggregateConfig from vidbyte/lib/dataclasses/multi_agent.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.dataclasses.multi_agent import AggregateConfig, ProposerSpec
from vidbyte.lib.errors import ConfigurationError

_MAX_NAME_CHARS = 256
_MAX_SYSTEM_PROMPT_CHARS = 500_000
_MAX_DESCRIPTION_CHARS = 2000
_MAX_LABEL_CHARS = 128


@dataclass(frozen=True, slots=True)
class AggregateAgentDescriptor:
    """Typed aggregate (mixture-of-agents) configuration loaded from a YAML document."""

    name: str = ""
    system_prompt: str = ""
    description: str = ""
    proposers: tuple[ProposerSpec, ...] = ()
    aggregator: ProposerSpec | None = None
    config: AggregateConfig = field(default_factory=AggregateConfig)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates identity, proposers list, label uniqueness, and config invariants.
        self._validate_identity()
        self._validate_proposers()
        self._validate_config()

    def to_agent_kwargs(self) -> dict[str, Any]:
        # Returns keyword arguments for AggregateAgent.__init__.
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "proposers": self.proposers,
            "aggregator": self.aggregator,
            "config": self.config,
            "metadata": dict(self.metadata),
        }

    def _validate_identity(self) -> None:
        # Validates name and system_prompt are non-empty and within length limits.
        if not self.name or not self.name.strip():
            raise ConfigurationError(
                "Aggregate agent name must be a non-empty string.",
                details={"field": "name", "expected": "non-empty string"},
            )
        if len(self.name) > _MAX_NAME_CHARS:
            raise ConfigurationError(
                f"Aggregate agent name must be at most {_MAX_NAME_CHARS} characters.",
                details={"field": "name", "max_chars": _MAX_NAME_CHARS, "actual_chars": len(self.name)},
            )
        if not self.system_prompt or not self.system_prompt.strip():
            raise ConfigurationError(
                "Aggregate agent system_prompt must be a non-empty string.",
                details={"field": "system_prompt", "expected": "non-empty string"},
            )
        if len(self.system_prompt) > _MAX_SYSTEM_PROMPT_CHARS:
            raise ConfigurationError(
                f"Aggregate agent system_prompt must be at most {_MAX_SYSTEM_PROMPT_CHARS} characters.",
                details={"field": "system_prompt", "max_chars": _MAX_SYSTEM_PROMPT_CHARS, "actual_chars": len(self.system_prompt)},
            )
        if len(self.description) > _MAX_DESCRIPTION_CHARS:
            raise ConfigurationError(
                f"Aggregate agent description must be at most {_MAX_DESCRIPTION_CHARS} characters.",
                details={"field": "description", "max_chars": _MAX_DESCRIPTION_CHARS, "actual_chars": len(self.description)},
            )

    def _validate_proposers(self) -> None:
        # Validates at least one proposer and no duplicate labels across proposers and aggregator.
        if not self.proposers:
            raise ConfigurationError(
                "Aggregate agent must have at least one proposer.",
                details={"field": "proposers", "expected": "at least one ProposerSpec"},
            )
        seen_labels: set[str] = set()
        for index, proposer in enumerate(self.proposers):
            if not proposer.provider or not proposer.provider.strip():
                raise ConfigurationError(
                    f"Proposer at index {index} must have a non-empty provider.",
                    details={"field": f"proposers[{index}].provider", "expected": "non-empty string"},
                )
            if not proposer.model or not proposer.model.strip():
                raise ConfigurationError(
                    f"Proposer at index {index} must have a non-empty model.",
                    details={"field": f"proposers[{index}].model", "expected": "non-empty string"},
                )
            label = proposer.label
            if label:
                if len(label) > _MAX_LABEL_CHARS:
                    raise ConfigurationError(
                        f"Proposer label '{label}' must be at most {_MAX_LABEL_CHARS} characters.",
                        details={"field": f"proposers[{index}].label", "max_chars": _MAX_LABEL_CHARS, "actual_chars": len(label)},
                    )
                if label in seen_labels:
                    raise ConfigurationError(
                        f"Duplicate proposer label '{label}' at index {index}.",
                        details={"field": f"proposers[{index}].label", "actual": label},
                    )
                seen_labels.add(label)
        if self.aggregator is not None:
            agg_label = self.aggregator.label
            if agg_label:
                if len(agg_label) > _MAX_LABEL_CHARS:
                    raise ConfigurationError(
                        f"Aggregator label '{agg_label}' must be at most {_MAX_LABEL_CHARS} characters.",
                        details={"field": "aggregator.label", "max_chars": _MAX_LABEL_CHARS, "actual_chars": len(agg_label)},
                    )
                if agg_label in seen_labels:
                    raise ConfigurationError(
                        f"Aggregator label '{agg_label}' conflicts with a proposer label.",
                        details={"field": "aggregator.label", "actual": agg_label},
                    )

    def _validate_config(self) -> None:
        # Validates aggregate config bounds against the proposer count.
        if self.config.min_successful > len(self.proposers):
            raise ConfigurationError(
                f"config.min_successful ({self.config.min_successful}) cannot exceed the number of proposers ({len(self.proposers)}).",
                details={
                    "field": "config.min_successful",
                    "actual": self.config.min_successful,
                    "max_proposers": len(self.proposers),
                },
            )
        if self.config.max_concurrency is not None and self.config.max_concurrency < 1:
            raise ConfigurationError(
                "config.max_concurrency must be at least 1 when provided.",
                details={"field": "config.max_concurrency", "actual": self.config.max_concurrency},
            )
        if self.config.per_proposer_timeout is not None and self.config.per_proposer_timeout <= 0:
            raise ConfigurationError(
                "config.per_proposer_timeout must be positive when provided.",
                details={"field": "config.per_proposer_timeout", "actual": self.config.per_proposer_timeout},
            )


__all__ = ["AggregateAgentDescriptor"]
