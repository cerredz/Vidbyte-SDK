"""Context Protocol Header

Description:
    Defines VerifierCollectionParams and VerifierCollection.
Purpose:
    Owns the set of verifiers for one target; runs them respecting
    dependency-derived tiers, short-circuiting later tiers on a blocking
    failure when configured to.
Architecture:
    - VerifierCollectionParams: validated dataclass — non-empty, unique
      names, every kind recognized, every depends_on resolvable, acyclic.
    - VerifierCollection: topological tiering + tiered async execution.
Relations:
    Consumes vidbyte.agents.runtimes.verifier.verifier.Verifier. Consumed by
    vidbyte.agents.runtimes.verifier.runtime.AgentVerifierRuntime.
Similar Files:
    - vidbyte/agents/contract.py: AgentLoopSettingsOutputContract, the
      nearest existing "owns a set of checks, runs them" class.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from vidbyte.agents.runtimes.verifier.types import VerifierCostClass, VerifierExecutionMode, VerifierKind, VerifierTarget, VerifierVerdict
from vidbyte.agents.runtimes.verifier.verifier import Verifier
from vidbyte.lib.errors import ConfigurationError

_COST_ORDER = {VerifierCostClass.LEAN: 0, VerifierCostClass.STANDARD: 1, VerifierCostClass.HEAVY: 2}


@dataclass(frozen=True, slots=True)
class VerifierCollectionParams:
    """Validated configuration for one VerifierCollection."""

    verifiers: tuple[Verifier, ...]
    execution_mode: VerifierExecutionMode = VerifierExecutionMode.PARALLEL_WITHIN_TIER
    stop_on_first_blocking_failure: bool = True

    def __post_init__(self) -> None:
        # Runs every structural check before this collection is allowed to exist.
        self._validate_non_empty()
        self._validate_unique_names()
        self._validate_known_kinds()
        self._validate_known_dependencies()
        self._validate_no_cycles()

    def _validate_non_empty(self) -> None:
        # An empty collection is a configuration mistake, not a valid "no checks" collection.
        if not self.verifiers:
            raise ConfigurationError("VerifierCollectionParams.verifiers must contain at least one Verifier.")

    def _validate_unique_names(self) -> None:
        # Duplicate names make depends_on and ledger reporting ambiguous.
        names = [v.params.name for v in self.verifiers]
        if len(names) != len(set(names)):
            raise ConfigurationError(f"VerifierCollectionParams.verifiers has duplicate names: {names}.")

    def _validate_known_kinds(self) -> None:
        # Implements the "verifiers must declare a keyword we offer" requirement.
        for verifier in self.verifiers:
            if verifier.params.kind not in VerifierKind:
                raise ConfigurationError(
                    f"Verifier '{verifier.params.name}' declares kind={verifier.params.kind!r}, which is not one "
                    f"of the supported VerifierKind values: {[k.value for k in VerifierKind]}."
                )

    def _validate_known_dependencies(self) -> None:
        # A depends_on entry naming a verifier that does not exist can never be satisfied.
        declared = {v.params.name for v in self.verifiers}
        for verifier in self.verifiers:
            unknown = set(verifier.params.depends_on) - declared
            if unknown:
                raise ConfigurationError(f"Verifier '{verifier.params.name}' depends_on unknown verifiers: {sorted(unknown)}.")

    def _validate_no_cycles(self) -> None:
        # A dependency cycle can never be topologically tiered, so it must be rejected up front.
        by_name = {v.params.name: v for v in self.verifiers}
        visited: set[str] = set()
        for verifier in self.verifiers:
            self._walk_for_cycle(verifier.params.name, by_name, visited, ())

    def _walk_for_cycle(self, name: str, by_name: dict[str, Verifier], visited: set[str], stack: tuple[str, ...]) -> None:
        # Depth-first walk that raises the instant a name reappears in its own ancestry.
        if name in stack:
            raise ConfigurationError(f"Verifier dependency cycle detected: {' -> '.join((*stack, name))}.")
        if name in visited:
            return
        visited.add(name)
        for dependency in by_name[name].params.depends_on:
            self._walk_for_cycle(dependency, by_name, visited, (*stack, name))


class VerifierCollection:
    """Runs a validated set of verifiers against one target, tier by tier."""

    def __init__(self, params: VerifierCollectionParams) -> None:
        # Caches the by-name lookup and the tier ordering derived from depends_on.
        self.params = params
        self._by_name = {v.params.name: v for v in params.verifiers}
        self._tiers = self._topological_tiers()

    async def run(self, target: VerifierTarget) -> tuple[VerifierVerdict, ...]:
        """Runs every applicable verifier against target, tier by tier, and returns every verdict gathered."""
        collected: list[VerifierVerdict] = []
        for tier in self._tiers:
            tier_verdicts = await self._run_tier(tier, target)
            collected.extend(tier_verdicts)
            if self.params.stop_on_first_blocking_failure and self._has_blocking_failure(tier_verdicts):
                break
        return tuple(collected)

    def by_name(self, name: str) -> Verifier | None:
        """Returns the verifier registered under name, or None if it is not part of this collection."""
        return self._by_name.get(name)

    def _topological_tiers(self) -> list[list[Verifier]]:
        # Groups verifiers by dependency depth so each tier can run only after every earlier tier finished.
        depth_cache: dict[str, int] = {}
        for verifier in self.params.verifiers:
            self._depth_of(verifier.params.name, depth_cache)
        tiers_by_depth: dict[int, list[Verifier]] = {}
        for verifier in self.params.verifiers:
            depth = depth_cache[verifier.params.name]
            tiers_by_depth.setdefault(depth, []).append(verifier)
        return [tiers_by_depth[depth] for depth in sorted(tiers_by_depth)]

    def _depth_of(self, name: str, depth_cache: dict[str, int]) -> int:
        # Memoized recursive depth computation; VerifierCollectionParams already guarantees no cycles.
        if name in depth_cache:
            return depth_cache[name]
        verifier = self._by_name[name]
        if not verifier.params.depends_on:
            depth_cache[name] = 0
            return 0
        depth = 1 + max(self._depth_of(dependency, depth_cache) for dependency in verifier.params.depends_on)
        depth_cache[name] = depth
        return depth

    @staticmethod
    def _has_blocking_failure(verdicts: list[VerifierVerdict]) -> bool:
        # A tier "fails" for short-circuit purposes only when a blocking verdict in it failed.
        return any(not verdict.passed and verdict.blocking for verdict in verdicts)

    async def _run_tier(self, tier: list[Verifier], target: VerifierTarget) -> list[VerifierVerdict]:
        # Filters to applicable verifiers, orders them, then dispatches sequentially or concurrently.
        applicable = [verifier for verifier in tier if verifier.applicable(target)]
        if not applicable:
            return []
        ordered = self._order_within_tier(applicable)
        if self.params.execution_mode is VerifierExecutionMode.SEQUENTIAL:
            return [await self._run_one(verifier, target) for verifier in ordered]
        return list(await asyncio.gather(*(self._run_one(verifier, target) for verifier in ordered)))

    def _order_within_tier(self, verifiers: list[Verifier]) -> list[Verifier]:
        # COST_ORDERED runs lean checks before heavy ones within the same dependency tier.
        if self.params.execution_mode is VerifierExecutionMode.COST_ORDERED:
            return sorted(verifiers, key=lambda verifier: _COST_ORDER[verifier.params.cost_class])
        return list(verifiers)

    async def _run_one(self, verifier: Verifier, target: VerifierTarget) -> VerifierVerdict:
        # Runs one verifier under its own timeout; a raised exception becomes a failing verdict, not a crash.
        started = time.monotonic()
        try:
            if verifier.params.timeout_seconds is not None:
                return await asyncio.wait_for(verifier.check(target), timeout=verifier.params.timeout_seconds)
            return await verifier.check(target)
        except Exception as exc:
            return VerifierVerdict(
                verifier_name=verifier.params.name,
                tier=verifier.params.tier,
                blocking=verifier.params.blocking,
                passed=False,
                score=None,
                diagnostics=f"{verifier.params.name} raised {type(exc).__name__}: {exc}",
                duration_seconds=time.monotonic() - started,
            )


__all__ = ["VerifierCollection", "VerifierCollectionParams"]
