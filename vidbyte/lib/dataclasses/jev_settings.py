"""FILE: vidbyte/lib/dataclasses/jev_settings.py

PURPOSE: Defines JevDecideSettings, the application-owned configuration for the jev_decide tool: which decision model to call and an optional confidence threshold.
ROLE IN CODEBASE: `vidbyte/tools/classifier/jev_decide.py` reads these settings to build its DecisionModelRunner lazily and to flag answers below the threshold.
ARCHITECTURE NOTE: Kept apart from vidbyte/lib/dataclasses/jev.py because it depends on model_configs; importing model_configs from jev.py would close an import cycle through ModalityDetector and lib.runners.types.
COMMON MODIFICATION PATTERNS: Add tool-level policy here; model transport settings belong on DecisionModelConfig.
KNOWN EDGE CASES: min_confidence defaults to None, meaning the tool never flags an answer; the API key is not resolved at construction, so settings build without credentials.
RELATED DOCS: docs/design/jev-decide-tool.md.
TESTS: tests/test_jev_decide_tool.py and scripts/test_jev_decide_tool.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vidbyte.lib.dataclasses.jev import JevProbability
from vidbyte.lib.dataclasses.model_configs import DecisionModelConfig
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class JevDecideSettings:
    """Application-owned settings for the jev_decide tool: the decision model and an optional threshold."""

    decision: DecisionModelConfig = field(default_factory=DecisionModelConfig)
    min_confidence: float | None = None

    def __post_init__(self) -> None:
        # Validates the optional threshold; the decision config validated its own shape.
        # @intent threshold-is-application-policy
        # min_confidence defaults to None because no replay evidence exists for any
        # threshold yet; the tool still reports the full distribution either way.
        if not isinstance(self.decision, DecisionModelConfig):
            raise ConfigurationError("decision must be a DecisionModelConfig.")
        if self.min_confidence is not None:
            object.__setattr__(self, "min_confidence", JevProbability.require(self.min_confidence, field_name="min_confidence"))


__all__ = ["JevDecideSettings"]
