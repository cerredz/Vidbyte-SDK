"""FILE: vidbyte/harnesses/stores/__init__.py

PURPOSE:
    Exposes local HarnessStore reference implementations from one stable package
    import without constructing either backend.

ROLE IN CODEBASE:
    Imported by vidbyte.harnesses, HarnessClient, and direct SDK callers. It
    depends only on memory.py and file.py and performs no persistence itself.

ARCHITECTURE NOTE:
    Database adapters remain outside this local-store package until the public
    run contract stabilizes.

PUBLIC API INVENTORY:
    FileHarnessStore and InMemoryHarnessStore.

COMMON MODIFICATION PATTERNS:
    Add an import and __all__ entry only after a new local backend implements the
    complete HarnessStore contract and is indexed in this folder's README.

WHAT NOT TO DO IN THIS FILE:
    1. Do not instantiate stores at import time.
    2. Do not import optional database drivers.
    3. Do not define persistence behavior in the export shim.

KNOWN EDGE CASES:
    Imports must remain safe when no filesystem path or external service exists.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Covered by public import smoke verification; no dedicated test file was added
    under the approved no-tests workflow.
"""

from __future__ import annotations

from vidbyte.harnesses.stores.file import FileHarnessStore
from vidbyte.harnesses.stores.memory import InMemoryHarnessStore

__all__ = ["FileHarnessStore", "InMemoryHarnessStore"]
