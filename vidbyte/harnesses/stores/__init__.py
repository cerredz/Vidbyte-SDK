"""FILE: vidbyte/harnesses/stores/__init__.py

PURPOSE:
    Exposes the TrajectorySink port and its local, dependency-free reference
    backends from one namespace. Mirrors vidbyte/sessions/stores/__init__.py.

ROLE IN CODEBASE:
    Import site for the harness trajectory export target(s). A sink is the LICENSED,
    redacted export surface, kept deliberately distinct from the operational
    vidbyte.sessions SessionStore.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md
"""

from __future__ import annotations

from vidbyte.harnesses.stores.base import TrajectorySink
from vidbyte.harnesses.stores.file import FileTrajectorySink
from vidbyte.harnesses.stores.memory import InMemoryTrajectorySink

__all__ = ["FileTrajectorySink", "InMemoryTrajectorySink", "TrajectorySink"]
