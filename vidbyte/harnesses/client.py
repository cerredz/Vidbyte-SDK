"""FILE: vidbyte/harnesses/client.py

PURPOSE:
    Thin SDK namespace exposed as sdk.harnesses. It provides the two persistence
    surfaces a harness binds (durable Session stores and licensed trajectory sinks),
    optional factory registration, a config-only load() convenience, and preserves
    the pre-existing durable Sessions namespace.

ROLE IN CODEBASE:
    The primary developer surface is subclassing vidbyte.harnesses.Harness and
    calling load()/execute() directly. This client is the plumbing that surface
    calls: store/sink constructors and a wrapper for foreign implementations.

ARCHITECTURE NOTE:
    Operational persistence (durable checkpoints + traces) and the licensed,
    redacted TrajectorySink are kept as DISTINCT surfaces on purpose so the
    consent/redaction boundary stays sharp. This client never mixes them.

PUBLIC API INVENTORY:
    HarnessClient.register(), load(), memory_store(), file_store(), memory_sink(),
    file_sink(), and the sessions attribute retained for backward compatibility.

WHAT NOT TO DO IN THIS FILE:
    1. Do not persist or execute during load().
    2. Do not create a global implementation registry.
    3. Do not remove or shadow sdk.harnesses.sessions.
    4. Do not blend the operational store with the licensed sink.

KNOWN EDGE CASES:
    load() requires either a direct foreign implementation or exactly one registered
    factory for the config's harness type; version now lives in code, so config-only
    resolution selects by type. A future WarehouseTrajectorySink implements the same
    TrajectorySink protocol with zero client changes.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Exercised by inline direct/registered/session/sink smoke checks; no dedicated
    test file was added under the approved no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vidbyte.harnesses.config import HarnessConfigLoader
from vidbyte.harnesses.execution import Harness, wrap_implementation
from vidbyte.harnesses.registry import HarnessFactory, HarnessRegistry
from vidbyte.harnesses.stores import (
    FileTrajectorySink,
    InMemoryTrajectorySink,
    TrajectorySink,
)
from vidbyte.sessions.client import SessionClient
from vidbyte.sessions.store import SessionStore
from vidbyte.sessions.stores.file import FileSessionStore
from vidbyte.sessions.stores.memory import InMemorySessionStore


class HarnessClient:
    """Namespace client for open harnesses over durable Sessions and consented export."""

    def __init__(self, *, registry: HarnessRegistry | None = None) -> None:
        # Creates a client-local registry and preserves sdk.harnesses.sessions.
        self.sessions = SessionClient()
        self._registry = registry or HarnessRegistry()

    def register(self, factory: HarnessFactory) -> None:
        # Registers one exact type/version implementation factory for this client only.
        self._registry.register(factory)

    def load(self, config: Mapping[str, Any] | str | Path, *, implementation: object | None = None, store: SessionStore | None = None, sink: TrajectorySink | None = None, collect: bool = False, base_path: str | Path | None = None) -> Harness:
        # Wraps a foreign implementation (or a registered factory) in the Harness envelope.
        if implementation is not None:
            harness = wrap_implementation(implementation, store=store, sink=sink, collect=collect)
            harness.load(config, base_path=base_path)
            return harness
        probe = HarnessConfigLoader().load(config, base_path=base_path)
        factory = self._registry.resolve_for_type(probe.harness_type)
        spec = HarnessConfigLoader().load(config, base_path=base_path, code_version=factory.harness_version)
        built = self._registry.create(spec)
        harness = wrap_implementation(built, store=store, sink=sink, collect=collect, harness_type=factory.harness_type, harness_version=factory.harness_version)
        harness.load(config, base_path=base_path)
        return harness

    def memory_store(self) -> InMemorySessionStore:
        # Creates an independent process-local durable session store.
        return InMemorySessionStore()

    def file_store(self, root: str | Path) -> FileSessionStore:
        # Creates an inspectable durable session store rooted at an explicit directory.
        return FileSessionStore(str(root))

    def memory_sink(self) -> InMemoryTrajectorySink:
        # Creates an independent process-local trajectory sink for inspection or testing.
        return InMemoryTrajectorySink()

    def file_sink(self, path: str | Path) -> FileTrajectorySink:
        # Creates an append-only JSONL trajectory sink at an explicit destination.
        return FileTrajectorySink(path)


__all__ = ["HarnessClient"]
