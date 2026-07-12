"""FILE: vidbyte/harnesses/client.py

PURPOSE:
    Provides the ergonomic SDK namespace for exact harness loading, optional
    factory registration, local store construction, execution-envelope creation,
    raw dataset export, and the pre-existing durable Sessions namespace.

ROLE IN CODEBASE:
    VidbyteSDK constructs HarnessClient as sdk.harnesses. The client composes the
    config loader, exact registry, serializer, stores, LoadedHarness, exporter,
    and SessionClient without executing a harness during load().

ARCHITECTURE NOTE:
    Every client owns one registry and one default memory store. Registration is
    optional because callers may pass any structural implementation directly.

PUBLIC API INVENTORY:
    HarnessClient.register(), load(), memory_store(), file_store(), export_jsonl(),
    and the sessions attribute retained for backward compatibility.

COMMON MODIFICATION PATTERNS:
    Keep this facade thin: validation and behavior belong in their owning modules.
    Add ergonomic constructors only for stores that implement the full public port.

WHAT NOT TO DO IN THIS FILE:
    1. Do not persist or execute during load().
    2. Do not create a global implementation registry.
    3. Do not select an implicit latest implementation version.
    4. Do not remove or shadow sdk.harnesses.sessions.

KNOWN EDGE CASES:
    The default memory store is shared by loaded harnesses from one client but not
    across clients or processes. A direct implementation bypasses factory creation,
    not config validation or the execution/persistence envelope.

COMMON ERRORS:
    HarnessConfigurationError for invalid enum/store choices and registry/config
    errors from their dedicated modules.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline direct/registered/default-store/session/export smoke checks;
    no dedicated test file was added under the approved no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from vidbyte.harnesses.config import HarnessConfigLoader
from vidbyte.harnesses.contracts import HarnessCaptureLevel, HarnessPersistenceMode, HarnessRunStatus
from vidbyte.harnesses.dataset import HarnessDatasetExporter
from vidbyte.harnesses.errors import HarnessConfigurationError
from vidbyte.harnesses.execution import LoadedHarness
from vidbyte.harnesses.registry import HarnessFactory, HarnessImplementation, HarnessRegistry
from vidbyte.harnesses.serialization import HarnessSerializer
from vidbyte.harnesses.store import HarnessStore
from vidbyte.harnesses.stores import FileHarnessStore, InMemoryHarnessStore
from vidbyte.sessions.client import SessionClient

E = TypeVar("E", bound=Enum)


class HarnessClient:
    """Namespace client for open harness implementations and canonical run capture."""

    def __init__(self, *, registry: HarnessRegistry | None = None, store: HarnessStore | None = None) -> None:
        # Creates client-local defaults and preserves sdk.harnesses.sessions.
        self.sessions = SessionClient()
        self._registry = registry or HarnessRegistry()
        self._serializer = HarnessSerializer()
        self._loader = HarnessConfigLoader()
        self._store = self._validate_store(store) if store is not None else InMemoryHarnessStore()

    def register(self, factory: HarnessFactory) -> None:
        # Registers one exact type/version implementation factory for this client only.
        self._registry.register(factory)

    def load(self, config: Mapping[str, Any] | str | Path, *, implementation: HarnessImplementation | None = None, store: HarnessStore | None = None, base_path: str | Path | None = None, capture: HarnessCaptureLevel | str = HarnessCaptureLevel.FULL, persistence: HarnessPersistenceMode | str = HarnessPersistenceMode.BEST_EFFORT, metadata: Mapping[str, Any] | None = None) -> LoadedHarness:
        # Resolves exact behavior and returns a side-effect-free configured envelope.
        spec = self._loader.load(config, base_path=base_path)
        selected_implementation = self._registry.create(spec) if implementation is None else self._registry.validate_implementation(implementation)
        selected_store = self._store if store is None else self._validate_store(store)
        capture_level = self._enum(HarnessCaptureLevel, capture, "capture")
        persistence_mode = self._enum(HarnessPersistenceMode, persistence, "persistence")
        return LoadedHarness(spec, selected_implementation, selected_store, serializer=self._serializer, capture_level=capture_level, persistence_mode=persistence_mode, metadata=metadata)

    def memory_store(self) -> InMemoryHarnessStore:
        # Creates an independent process-local canonical harness store.
        return InMemoryHarnessStore()

    def file_store(self, root: str | Path) -> FileHarnessStore:
        # Creates an inspectable local store without writing until first execution.
        return FileHarnessStore(root, serializer=self._serializer)

    async def export_jsonl(self, store: HarnessStore, path: str | Path, *, spec_id: str | None = None, statuses: Sequence[HarnessRunStatus | str] | None = None) -> int:
        # Exports selected specs, runs, and ordered events as standalone raw rows.
        selected_store = self._validate_store(store)
        return await HarnessDatasetExporter(selected_store, serializer=self._serializer).export_jsonl(path, spec_id=spec_id, statuses=statuses)

    def _validate_store(self, store: object) -> HarnessStore:
        # Requires the complete structural async persistence surface at composition time.
        if not isinstance(store, HarnessStore):
            raise HarnessConfigurationError("Harness store does not implement the complete HarnessStore contract.", details={"actual_type": type(store).__name__})
        return store

    def _enum(self, enum_type: type[E], value: E | str, field: str) -> E:
        # Normalizes public string enum choices and reports every supported value.
        try:
            return value if isinstance(value, enum_type) else enum_type(value)
        except (TypeError, ValueError) as exc:
            raise HarnessConfigurationError("Harness load option is unsupported.", details={"field": field, "value": str(value), "allowed": [item.value for item in enum_type]}) from exc


__all__ = ["HarnessClient"]
