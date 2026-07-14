"""Context Protocol Header

Path: vidbyte/procedures/stores/__init__.py
Purpose: Export the reference ephemeral and durable procedure store adapters.
Architecture: Keeps backend selection explicit while ProcedureLibrary depends only on
the ProcedureStore protocol.
Exports: InMemoryProcedureStore and FileProcedureStore.
Invariants: Importing this package performs no store I/O or root creation.
Do not: Add ranking, promotion, or active-head policy to this namespace.
Related: vidbyte/procedures/store.py and vidbyte/procedures/README.md.
Tests: Existing import verification; no new tests by approved workflow.
"""

from vidbyte.procedures.stores.file import FileProcedureStore
from vidbyte.procedures.stores.memory import InMemoryProcedureStore

__all__ = ["FileProcedureStore", "InMemoryProcedureStore"]
