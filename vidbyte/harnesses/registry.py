"""FILE: vidbyte/harnesses/registry.py

PURPOSE:
    Defines the minimal structural protocol arbitrary harness code must satisfy
    and the exact type/version factory registry used for config-only loading.
    This file preserves implementation openness and performs no execution.

ROLE IN CODEBASE:
    HarnessClient accepts direct HarnessImplementation objects or asks
    HarnessRegistry to create one from a HarnessSpec. The Harness execution
    envelope later calls the validated run method. Depends only on contracts/errors.

ARCHITECTURE NOTE:
    Registration is optional, client-local, and exact. There is no inheritance
    requirement, global registry, dynamic import, or implicit latest-version
    fallback. See docs/design/harness-execution-contract.md.

PUBLIC API INVENTORY:
    HarnessImplementation.run(request); HarnessFactory.create(spec);
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
    Structural validation proves only that run is callable; implementation
    correctness is observed inside the execution envelope and recorded as a run.
    Factories receive a defensive copy and mutation is rejected so construction
    cannot silently diverge from the recorded specification.

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

from copy import deepcopy
from typing import Any, Protocol, runtime_checkable

from vidbyte.harnesses.contracts import HarnessSpec
from vidbyte.harnesses.errors import (
    HarnessConfigurationError,
    HarnessDuplicateRegistrationError,
    HarnessRegistrationError,
)


@runtime_checkable
class HarnessImplementation(Protocol):
    """Open structural contract for arbitrary synchronous or asynchronous harnesses.

    This is the low-level seam: the concrete `Harness` base class in execution.py
    implements it and adds load()/version/session ergonomics, while a foreign object
    with a callable `run(request)` still works without inheriting anything. Per-agent
    trajectory capture is not part of this seam; implementations obtain durable
    Sessions from `Harness.session(agent)` (or bind their own SessionStore).
    """

    def run(self, request: Any) -> Any:
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
        # Accepts any object with a callable run method and rejects wider assumptions.
        run = getattr(implementation, "run", None)
        if not callable(run):
            raise HarnessRegistrationError("Harness implementation must expose callable run(request).", details={"actual_type": type(implementation).__name__})
        return implementation  # type: ignore[return-value]

    def resolve_for_type(self, harness_type: str) -> HarnessFactory:
        # Selects the sole factory for one type; version now lives in code, not config.
        matches = [factory for (registered_type, _version), factory in self._factories.items() if registered_type == harness_type]
        if not matches:
            raise HarnessRegistrationError("No harness factory is registered for this type.", details={"harness_type": harness_type, "known_types": self.known_types()})
        if len(matches) > 1:
            raise HarnessRegistrationError("Multiple factory versions are registered for this type; pass implementation= explicitly.", details={"harness_type": harness_type, "known_versions": self.known_versions(harness_type)})
        return matches[0]

    def known_types(self) -> tuple[str, ...]:
        # Lists registered harness types in stable order.
        return tuple(sorted({registered_type for registered_type, _version in self._factories}))

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
        factory_spec = deepcopy(spec)
        try:
            implementation = factory.create(factory_spec)
        except Exception as exc:
            raise HarnessConfigurationError("Harness factory could not construct its implementation.", details={"harness_type": spec.harness_type, "harness_version": spec.harness_version, "factory_type": type(factory).__name__}) from exc
        if factory_spec != spec:
            raise HarnessConfigurationError("Harness factory mutated its immutable specification during construction.", details={"harness_type": spec.harness_type, "harness_version": spec.harness_version, "factory_type": type(factory).__name__})
        return implementation


__all__ = ["HarnessFactory", "HarnessImplementation", "HarnessRegistry"]
