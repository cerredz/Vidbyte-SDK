"""Context Protocol Header

Description:
    Defines the Verifier base class, plus CallableVerifier.
Purpose:
    A verifier is one deterministic check: it takes a VerifierTarget and
    returns a VerifierVerdict. CallableVerifier wraps a plain function so the
    collection is runnable without a full concrete subclass per VerifierKind.
Architecture note:
    - Verifier: abstract base — check()/applicable()/describe().
    - CallableVerifier: wraps a sync or async predicate/verdict function.
    VerifierParams (validated dataclass: name, kind, cost_class, tier,
    blocking, depends_on, timeout_seconds) lives in
    vidbyte.lib.dataclasses.verifier, not here, per review feedback on
    PR #349.
Relations:
    Consumed by vidbyte.agents.runtimes.verifier.collection.VerifierCollection.
Similar Files:
    - vidbyte/agents/contracts/__init__.py: OutputContract, the nearest
      existing "small declarative check" base class in this repo.
Role in codebase:
    Defines the single-check contract consumed by VerifierCollection.
Common modification patterns:
    Add deterministic verifier behavior through a Verifier subclass or
    CallableVerifier wrapper.
Known edge cases:
    A verifier may be inapplicable; that outcome must remain distinct from a
    failed check.
Related docs:
    docs/design/verifier-runtime.md
Tests:
    Covered by verifier contract and collection tests.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable

from vidbyte.lib.dataclasses.verifier import VerifierParams, VerifierTarget, VerifierVerdict


class Verifier:
    """Base class for one deterministic check. Subclass and implement check()."""

    def __init__(self, params: VerifierParams) -> None:
        # Stores the already-validated configuration for this verifier instance.
        self.params = params

    async def check(self, target: VerifierTarget) -> VerifierVerdict:
        """Runs this verifier's check against target and returns its verdict."""
        raise NotImplementedError(f"{type(self).__name__} must implement check().")

    def applicable(self, target: VerifierTarget) -> bool:
        """Returns whether this verifier should run at all against target."""
        del target
        return True

    def describe(self) -> str:
        """Returns a short human-readable description of this verifier."""
        return f"{self.params.name} ({self.params.kind.value})"


class CallableVerifier(Verifier):
    """Wraps a plain function as a Verifier, so the collection is runnable without a full subclass."""

    def __init__(self, params: VerifierParams, fn: Callable[[VerifierTarget], object]) -> None:
        # Stores the wrapped function alongside the base verifier configuration.
        super().__init__(params)
        self._fn = fn

    async def check(self, target: VerifierTarget) -> VerifierVerdict:
        """Calls the wrapped function and normalizes its return value into a VerifierVerdict."""
        started = time.monotonic()
        result = await self._call_fn(target)
        return self._to_verdict(result, duration_seconds=time.monotonic() - started)

    async def _call_fn(self, target: VerifierTarget) -> object:
        # Awaits the wrapped function's result if it returned a coroutine.
        result = self._fn(target)
        if inspect.isawaitable(result):
            return await result
        return result

    def _to_verdict(self, result: object, *, duration_seconds: float) -> VerifierVerdict:
        # Accepts either a bare bool or an already-built VerifierVerdict from the wrapped function.
        if isinstance(result, VerifierVerdict):
            return result
        passed = bool(result)
        diagnostics = "" if passed else f"{self.params.name} returned a falsy result."
        return VerifierVerdict(
            verifier_name=self.params.name,
            tier=self.params.tier,
            blocking=self.params.blocking,
            passed=passed,
            score=None,
            diagnostics=diagnostics,
            duration_seconds=duration_seconds,
        )


__all__ = ["CallableVerifier", "Verifier", "VerifierParams"]
