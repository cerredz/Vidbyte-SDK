"""FILE: vidbyte/workflows/stores/__init__.py
PURPOSE: Routes callers to bundled workflow persistence adapters.
ROLE IN CODEBASE: Re-exports memory.py and file.py; storage contracts live in persistence.py.

ARCHITECTURE NOTE:
    This folder contains persistence mechanisms only. Event meaning belongs in
    events.py/projection.py, and execution belongs in machine.py.

PUBLIC API INVENTORY:
    InMemoryWorkflowStore: Concurrent process-local append-only store.
    FileWorkflowStore: Inspectable atomic filesystem-backed durable store.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add projection or execution behavior.
    2. Do not alias agent SessionStore implementations as WorkflowStore.

KNOWN EDGE CASES:
    File storage is not a distributed database and cannot provide cross-host locking.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; adapters are covered by inline round-trip smoke.
"""

from .file import FileWorkflowStore
from .memory import InMemoryWorkflowStore

__all__ = ["FileWorkflowStore", "InMemoryWorkflowStore"]
