"""Registry for built-in semantic trace components."""

from __future__ import annotations

from dataclasses import dataclass, field

from vidbyte.lib.errors import ConfigurationError
from vidbyte.trace.schema import SpanSpec


@dataclass(slots=True)
class TraceComponentRegistry:
    """Small registry for component span specs used by tests and docs."""

    _specs: dict[str, SpanSpec] = field(default_factory=dict)

    def register(self, spec: SpanSpec) -> None:
        # Registers one span spec and rejects duplicate names.
        if spec.name in self._specs:
            raise ConfigurationError(f"Trace span spec already registered: {spec.name}.")
        self._specs[spec.name] = spec

    def get(self, name: str) -> SpanSpec:
        # Returns a registered span spec or raises for unknown names.
        try:
            return self._specs[name]
        except KeyError as exc:
            raise ConfigurationError(f"Unknown trace span spec: {name}.") from exc

    def all(self) -> tuple[SpanSpec, ...]:
        # Returns all registered specs in insertion order.
        return tuple(self._specs.values())


__all__ = ["TraceComponentRegistry"]
