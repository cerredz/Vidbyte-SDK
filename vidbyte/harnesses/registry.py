"""FILE: vidbyte/harnesses/registry.py

PURPOSE:
    Defines the minimal structural protocol arbitrary harness code must satisfy
    and the exact type/version factory registry used for config-only loading.
    This file preserves implementation openness and performs no execution.

ROLE IN CODEBASE:
    HarnessClient accepts direct HarnessImplementation objects or asks
    HarnessRegistry to create one from a HarnessSpec. LoadedHarness later calls
    the validated execute method. The registry depends only on contracts/errors.

ARCHITECTURE NOTE:
    Registration is optional, client-local, and exact. There is no inheritance
    requirement, global registry, dynamic import, or implicit latest-version
    fallback. See docs/design/harness-execution-contract.md.

PUBLIC API INVENTORY:
    HarnessImplementation.execute(request, context); HarnessFactory.create(spec);
    HarnessRegistry.register(), create(), validate_implementation(), and
    known_versions().

COMMON MODIFICATION PATTERNS:
    Add discovery mechanisms outside this registry and translate them into an
    explicit factory registration. Keep exact version selection stable.

WHAT NOT TO DO IN THIS FILE:
    1. Do not import implementations from dotted config paths.
    2. Do not add agent-loop or orchestration requirements to the protocol.
    3. Do not silently replace an existing factory or select a latest version.

KNOWN EDGE CASES:
    Structural validation proves only that execute is callable; implementation
    correctness is observed inside the execution envelope and recorded as a run.

COMMON ERRORS:
    HarnessDuplicateRegistrationError for key collisions;
    HarnessRegistrationError for missing/invalid factories;
    HarnessConfigurationError when factory construction fails.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by direct and registered implementation smoke verification; no
    dedicated test file was added under the approved no-tests workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from vidbyte.harnesses.contracts import HarnessSpec
from vidbyte.harnesses.errors import (
    HarnessConfigurationError,
    HarnessDuplicateRegistrationError,
    HarnessRegistrationError,
)

if TYPE_CHECKING:
    from vidbyte.harnesses.execution import HarnessContext


@runtime_checkable
class HarnessImplementation(Protocol):
    """Open structural contract for arbitrary synchronous or asynchronous harnesses."""

    def execute(self, request: Any, context: "HarnessContext") -> Any:
        # Runs implementation-specific logic and returns either a value or awaitable.
        ...


@runtime_checkable
class HarnessFactory(Protocol):
    """Exact type/version factory used for config-only harness loading."""

    harness_type: str
    harness_version: str

    def create(self, spec: HarnessSpec) -> HarnessImplementation:
        # Builds one implementation from the resolved exact specification.
        ...


class HarnessRegistry:
    """Client-local registry keyed by exact harness type and version."""

    def __init__(self) -> None:
        # Initializes an empty exact factory map without global side effects.
        self._factories: dict[tuple[str, str], HarnessFactory] = {}

    def register(self, factory: HarnessFactory) -> None:
        # Validates and stores one factory while refusing implicit replacement.
        key = self._factory_key(factory)
        if key in self._factories:
            raise HarnessDuplicateRegistrationError("Harness factory is already registered.", details={"harness_type": key[0], "harness_version": key[1]})
        self._factories[key] = factory

    def create(self, spec: HarnessSpec) -> HarnessImplementation:
        # Resolves the exact spec key and validates the constructed implementation.
        key = (spec.harness_type, spec.harness_version)
        factory = self._factories.get(key)
        if factory is None:
            raise HarnessRegistrationError("No harness factory is registered for this exact type and version.", details={"harness_type": key[0], "harness_version": key[1], "known_versions": self.known_versions(key[0])})
        implementation = self._create_from_factory(factory, spec)
        return self.validate_implementation(implementation)

    def validate_implementation(self, implementation: object) -> HarnessImplementation:
        # Accepts any object with a callable execute method and rejects wider assumptions.
        execute = getattr(implementation, "execute", None)
        if not callable(execute):
            raise HarnessRegistrationError("Harness implementation must expose callable execute(request, context).", details={"actual_type": type(implementation).__name__})
        return implementation  # type: ignore[return-value]

    def known_versions(self, harness_type: str) -> tuple[str, ...]:
        # Lists registered exact versions for one type in stable order.
        return tuple(sorted(version for registered_type, version in self._factories if registered_type == harness_type))

    def _factory_key(self, factory: HarnessFactory) -> tuple[str, str]:
        # Extracts and validates a factory's stable identity attributes and create seam.
        harness_type = getattr(factory, "harness_type", None)
        harness_version = getattr(factory, "harness_version", None)
        create = getattr(factory, "create", None)
        if not isinstance(harness_type, str) or not harness_type.strip():
            raise HarnessRegistrationError("Harness factory requires a non-empty harness_type.", details={"actual_type": type(harness_type).__name__})
        if not isinstance(harness_version, str) or not harness_version.strip():
            raise HarnessRegistrationError("Harness factory requires a non-empty harness_version.", details={"actual_type": type(harness_version).__name__})
        if not callable(create):
            raise HarnessRegistrationError("Harness factory requires callable create(spec).", details={"factory_type": type(factory).__name__})
        return harness_type.strip(), harness_version.strip()

    def _create_from_factory(self, factory: HarnessFactory, spec: HarnessSpec) -> HarnessImplementation:
        # Converts factory construction failures into configuration context at load time.
        try:
            return factory.create(spec)
        except Exception as exc:
            raise HarnessConfigurationError("Harness factory could not construct its implementation.", details={"harness_type": spec.harness_type, "harness_version": spec.harness_version, "factory_type": type(factory).__name__}) from exc


__all__ = ["HarnessFactory", "HarnessImplementation", "HarnessRegistry"]
