"""FILE: vidbyte/workflows/routing.py
PURPOSE: Adapts synchronous and asynchronous branch functions to the Router protocol.
ROLE IN CODEBASE: Stored in branch definitions by graph.py and invoked against validated candidates by machine.py.

ARCHITECTURE NOTE:
    A router returns only a semantic branch key. The compiled branch map remains
    the authority that resolves that key to a target and guards, which prevents
    callback or model output from acquiring arbitrary jump authority.

PUBLIC API INVENTORY:
    CallableRouter: Invokes one sync/async RoutingContext callback and returns its key.

COMMON MODIFICATION PATTERNS:
    Add a specialized router only when it preserves bounded-key semantics.
    Declare keys and destinations through StateGraph.add_branch().

WHAT NOT TO DO IN THIS FILE:
    1. Do not accept or return target stage objects.
    2. Do not provide an implicit default destination.
    3. Do not validate or commit candidate state.

KNOWN EDGE CASES:
    Empty and undeclared keys are rejected by machine.py with WorkflowRoutingError.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/validated-state-machine-workflows.md

TESTS:
    No feature-specific test file is added by the approved no-tests design.
    Inline smoke covers synchronous, asynchronous, and undeclared branch keys.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Generic

from vidbyte.workflows.contracts import RoutingContext, StateT
from vidbyte.workflows.errors import WorkflowDefinitionError


class CallableRouter(Generic[StateT]):
    """Adapts one synchronous or asynchronous bounded branch callback."""

    def __init__(self, callback: Callable[[RoutingContext[StateT]], str | Awaitable[str]], *, name: str | None = None) -> None:
        # Stores one branch callback and a stable diagnostic name.
        if not callable(callback):
            raise WorkflowDefinitionError("CallableRouter callback must be callable.", details={"actual_type": type(callback).__name__})
        self._callback = callback
        candidate = name or getattr(callback, "__name__", None) or "callable_router"
        self._name = str(candidate).strip()
        if not self._name:
            raise WorkflowDefinitionError("CallableRouter name cannot be empty.", details={"adapter": "callable_router"})

    @property
    def name(self) -> str:
        # Returns the stable identifier used in routing diagnostics.
        return self._name

    async def route(self, context: RoutingContext[StateT]) -> str:
        # Invokes the callback and awaits it only when necessary.
        value = self._callback(context)
        return await value if inspect.isawaitable(value) else value


__all__ = ["CallableRouter"]
