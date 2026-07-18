"""Context Protocol Header

Description:
    Defines EnvironmentRegistry, the class-level name registry for environment
    implementations.
Purpose:
    Makes environments addressable by name so CLIs, services, and skills can
    discover and instantiate them without importing concrete classes directly.
Architecture:
    - EnvironmentRegistry: register / get / create / names classmethods.
Relations:
    Registers subclasses of vidbyte.environments.base.Environment; consumed by
    the EnvironmentsClient namespace.
Similar Files:
    - vidbyte/lib/registries/models.py: Registry conventions this mirrors.
"""

from __future__ import annotations

from typing import Any, ClassVar

from vidbyte.environments.base import Environment
from vidbyte.lib.errors import ConfigurationError


class EnvironmentRegistry:
    """Class-level registry of environment implementations keyed by name."""

    _registry: ClassVar[dict[str, type[Environment]]] = {}

    @classmethod
    def register(cls, environment_cls: type[Environment], *, replace: bool = False) -> type[Environment]:
        """Register an environment class under its declared name; usable as a decorator."""
        name = environment_cls.name
        if name == Environment.name:
            raise ConfigurationError(
                "Environments must declare a unique class-level name before registration."
            )
        if name in cls._registry and not replace:
            raise ConfigurationError(f"Environment already registered: '{name}'. Pass replace=True to override.")
        cls._registry[name] = environment_cls
        return environment_cls

    @classmethod
    def get(cls, name: str) -> type[Environment]:
        """Return the registered environment class for a name."""
        try:
            return cls._registry[name]
        except KeyError as exc:
            raise ConfigurationError(
                f"Unknown environment '{name}'. Registered environments: {', '.join(sorted(cls._registry)) or 'none'}."
            ) from exc

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> Environment:
        """Instantiate the registered environment class for a name."""
        return cls.get(name)(**kwargs)

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Return every registered environment name in sorted order."""
        return tuple(sorted(cls._registry))


__all__ = [
    "EnvironmentRegistry",
]
