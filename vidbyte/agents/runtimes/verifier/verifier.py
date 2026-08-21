"""Context Protocol Header

Description:
    Defines VerifierParams and the Verifier base class, plus CallableVerifier.
Purpose:
    A verifier is one deterministic check: it takes a VerifierTarget and
    returns a VerifierVerdict. CallableVerifier wraps a plain function so the
    collection is runnable without a full concrete subclass per VerifierKind.
Architecture:
    - VerifierParams: validated dataclass (name, kind, cost_class, tier,
      blocking, depends_on, timeout_seconds).
    - Verifier: abstract base — check()/applicable()/describe().
    - CallableVerifier: wraps a sync or async predicate/verdict function.
Relations:
    Consumed by vidbyte.agents.runtimes.verifier.collection.VerifierCollection.
Similar Files:
    - vidbyte/agents/contracts/__init__.py: OutputContract, the nearest
      existing "small declarative check" base class in this repo.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from vidbyte.agents.runtimes.verifier.types import VerifierCostClass, VerifierKind, VerifierTarget, VerifierVerdict
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class VerifierParams:
    """Validated configuration for one Verifier instance."""

    name: str
    kind: VerifierKind
    cost_class: VerifierCostClass = VerifierCostClass.STANDARD
    tier: int = 0
    blocking: bool = True
    depends_on: tuple[str, ...] = ()
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        # Rejects a blank name, a kind that is not a real VerifierKind member, and a non-positive timeout.
        self._validate_name()
        self._validate_kind()
        self._validate_timeout()

    def _validate_name(self) -> None:
        # A verifier without a name cannot be addressed by depends_on or reported in feedback.
        if not self.name.strip():
            raise ConfigurationError("VerifierParams.name must be a non-empty string.")

    def _validate_kind(self) -> None:
        # Every verifier must declare one of the SDK's supported kinds.
        if not isinstance(self.kind, VerifierKind):
            raise ConfigurationError(f"VerifierParams.kind must be a VerifierKind member, got {self.kind!r}.")

    def _validate_timeout(self) -> None:
        # A zero or negative timeout would never let the check run.
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ConfigurationError("VerifierParams.timeout_seconds must be greater than zero when provided.")


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
