"""Context Protocol Header

Description:
    Defines the HarnessDescriptor dataclass for YAML-loaded harness configurations.
Purpose:
    Provides a single typed object that the YamlLoader produces when it reads a
    harness YAML document. The descriptor holds a params schema and a nested agent
    config; it is pure data — no runtime behavior.
Architecture:
    - HarnessDescriptor: frozen dataclass with name, description, params schema dict,
      and an optional AgentDescriptor for the harness's internal agent.
Relations:
    - Produced by vidbyte/lib/config/loader.py.
    - Composes AgentDescriptor from vidbyte/lib/dataclasses/agent_descriptor.py.
    - The runtime Harness ABC lives in vidbyte-harnesses (separate repo).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.agent_descriptor import AgentDescriptor

_VALID_PARAM_TYPES = frozenset({"str", "int", "float", "bool", "list[str]", "list[int]", "list[float]"})


@dataclass(frozen=True, slots=True)
class HarnessDescriptor:
    """Typed harness configuration loaded from a YAML document."""

    name: str = ""
    description: str = ""
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent: "AgentDescriptor | None" = None

    def __post_init__(self) -> None:
        # Validates harness identity, description length, and params schema shape.
        if not self.name or not self.name.strip():
            raise ConfigurationError(
                "Harness name must be a non-empty string.",
                details={"field": "name", "expected": "non-empty string"},
            )
        if len(self.name) > 128:
            raise ConfigurationError(
                "Harness name must be at most 128 characters.",
                details={"field": "name", "max_chars": 128, "actual_chars": len(self.name)},
            )
        if not self.description or not self.description.strip():
            raise ConfigurationError(
                "Harness description must be a non-empty string.",
                details={"field": "description", "expected": "non-empty string"},
            )
        if len(self.description) > 2000:
            raise ConfigurationError(
                "Harness description must be at most 2000 characters.",
                details={"field": "description", "max_chars": 2000, "actual_chars": len(self.description)},
            )
        self._validate_params(self.params)

    @staticmethod
    def _validate_params(params: dict[str, dict[str, Any]]) -> None:
        # Rejects malformed param schemas: missing type, invalid type, bad name, type-mismatched defaults.
        for param_name, schema in params.items():
            if not isinstance(schema, dict):
                raise ConfigurationError(
                    f"Harness param '{param_name}' must be a mapping.",
                    details={"field": f"params.{param_name}", "expected": "mapping"},
                )
            if not param_name or not param_name.strip():
                raise ConfigurationError(
                    "Harness param names must be non-empty.",
                    details={"field": "params", "expected": "non-empty param name"},
                )
            if len(param_name) > 64:
                raise ConfigurationError(
                    f"Harness param name '{param_name}' must be at most 64 characters.",
                    details={"field": f"params.{param_name}", "max_chars": 64},
                )
            param_type = schema.get("type")
            if not param_type or param_type not in _VALID_PARAM_TYPES:
                raise ConfigurationError(
                    f"Harness param '{param_name}' must have a valid type.",
                    details={
                        "field": f"params.{param_name}.type",
                        "actual": param_type,
                        "expected": sorted(_VALID_PARAM_TYPES),
                    },
                )
            if "default" in schema:
                default = schema["default"]
                if not HarnessDescriptor._default_matches_type(default, param_type):
                    raise ConfigurationError(
                        f"Harness param '{param_name}' default value does not match declared type '{param_type}'.",
                        details={
                            "field": f"params.{param_name}.default",
                            "actual_type": type(default).__name__,
                            "expected": param_type,
                        },
                    )

    @staticmethod
    def _default_matches_type(value: Any, param_type: str) -> bool:
        # Checks that a default value is compatible with the declared param type.
        if param_type == "str":
            return isinstance(value, str)
        if param_type == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        if param_type == "float":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if param_type == "bool":
            return isinstance(value, bool)
        if param_type.startswith("list["):
            return isinstance(value, list)
        return False


__all__ = ["HarnessDescriptor"]
