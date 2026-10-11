"""FILE: vidbyte/harnesses/execution.py

PURPOSE:
    Defines the concrete `Harness` base class: the developer-facing surface that
    owns config loading, deterministic identity, the run lifecycle, and automatic
    trajectory collection. An author subclasses it, declares code `type`/`version`,
    and overrides `run(request)`; the SDK owns everything around that method.

ROLE IN CODEBASE:
    `Harness` implements the low-level `HarnessImplementation` protocol (registry.py)
    and composes vidbyte.sessions for durable per-agent capture, TrajectoryCollector
    for run-boundary aggregation, and a TrajectorySink for consented export.

ARCHITECTURE NOTE:
    Persistence is not reinvented here. Sessions already persist a checkpoint per
    turn with full traces onto a durable SessionStore; this envelope only assigns a
    run identity, fans those sessions in by tag, and — under an explicit consent
    flag — hands one redacted TrajectoryRecord to the sink in a fail-open `finally`.
    Collection must NEVER fail the run. See the approved design document.

PUBLIC API INVENTORY:
    Harness.load(), execute(), session(agent), run(request) [override], score()
    [optional override], and the spec/store/run_id properties.
    wrap_implementation() adapts a foreign object with run(request) into a Harness.

WHAT NOT TO DO IN THIS FILE:
    1. Do not build a second event/store system; bind a SessionStore instead.
    2. Do not let a collection or sink error propagate out of execute().
    3. Do not keep the active run_id in shared instance state; overlapping
       execute() calls on one instance must each keep their own run_id.

KNOWN EDGE CASES:
    Synchronous run() bodies cannot be interrupted by an asyncio timeout while
    blocking. Cancellation and timeout cannot fence side effects already started.
    session() is only valid during execute(), when a run_id exists. Code run in a
    plain thread (no copied context) falls back to the lone in-flight run_id.

COMMON ERRORS:
    HarnessConfigurationError before load(); HarnessExecutionError for run()
    failures; HarnessTimeoutError for explicit deadlines.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    tests/test_harness_execution.py covers overlapping executions on one instance.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import math
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

from vidbyte.harnesses.config import HarnessConfigLoader
from vidbyte.harnesses.contracts import HARNESS_SCHEMA_VERSION, HarnessExecutionResult, HarnessRun, HarnessRunStatus, HarnessSpec
from vidbyte.harnesses.dataset import TrajectoryCollector
from vidbyte.harnesses.errors import HarnessConfigurationError, HarnessExecutionError, HarnessTimeoutError
from vidbyte.harnesses.serialization import HarnessRedactor
from vidbyte.harnesses.stores import TrajectorySink
from vidbyte.sessions.session import Session
from vidbyte.sessions.store import SessionStore
from vidbyte.sessions.stores.memory import InMemorySessionStore

if False:  # pragma: no cover - typing only, avoids importing the heavy agent base
    from vidbyte.agents.base import BaseAgent


class _HarnessDeadlineExpired(Exception):
    """Private marker distinguishing the SDK deadline from implementation timeouts."""


def _utc_now() -> str:
    # Produces a timezone-aware portable timestamp for every run boundary.
    return datetime.now(timezone.utc).isoformat()


class Harness:
    """Concrete base class an author subclasses to get a durable, collectible harness.

    Example:
        class ResearchSwarm(Harness):
            type = "research-swarm"   # matches config harness.type
            version = "2"             # code identity; NOT in the YAML

            async def run(self, request):
                planner = self.session(build_planner())   # full-trace, tagged session
                await planner.arun(request["topic"])
                return {"answer": "..."}

        h = ResearchSwarm(store=store, sink=sink, collect=True)
        h.load("harness.yaml")
        result = await h.execute({"topic": "durable runtimes"})
    """

    type: ClassVar[str] = ""
    version: ClassVar[str] = ""

    def __init__(self, *, store: SessionStore | None = None, sink: TrajectorySink | None = None, collect: bool = False) -> None:
        # Binds the two persistence surfaces once and the per-run/tenant consent flag.
        self._store: SessionStore = store or InMemorySessionStore()   # operational source of truth
        self._sink = sink                                             # LICENSED, redacted, sellable derivative
        self._collect = bool(collect)                                # opt-in consent, default off
        self._redactor = HarnessRedactor()
        self._spec: HarnessSpec | None = None
        # @intent overlapping-executions-keep-their-own-run-id
        # Each execute() (asyncio Task) sees only its own run_id, so overlapping trials on one
        # instance never tag, list, or collect each other's sessions.
        self._run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(f"vidbyte_harness_run_id_{id(self)}", default=None)
        self._active_run_ids: list[str] = []   # in-flight executions, for readers outside their context

    # --- configuration & identity ------------------------------------------------

    def load(self, config: Mapping[str, Any] | str | Path, *, base_path: str | Path | None = None) -> "Harness":
        # Validates/resolves the YAML and computes spec_id, folding in this class's code version.
        self._spec = HarnessConfigLoader().load(config, base_path=base_path, code_version=type(self).version)
        return self

    @property
    def spec(self) -> HarnessSpec:
        # Returns the exact loaded specification (raises if load() has not run).
        if self._spec is None:
            raise HarnessConfigurationError("Harness.load(...) must be called before reading spec.")
        return self._spec

    @property
    def store(self) -> SessionStore:
        # Returns the operational session store bound to this harness.
        return self._store

    @property
    def run_id(self) -> str | None:
        # Returns the current unique execution id while execute() is running.
        return self._current_run_id()

    # --- developer seams ---------------------------------------------------------

    def session(self, agent: "BaseAgent") -> Session:
        # Auto-instrument seam: full-fidelity capture is forced, no tracing code needed.
        # The run_id tag is the fan-in that later reconstructs the whole multi-agent run.
        run_id = self._current_run_id()
        if run_id is None:
            raise HarnessConfigurationError("Harness.session(agent) is only available during execute().")
        return Session(
            agent,
            store=self._store,
            policy=Session.PER_STEP_POLICY,   # intermediate decisions, not just final turns
            trace=Session.FULL_TRACE,          # trace_events + artifact captured per checkpoint
            tags=[run_id],                     # fan-in key across all agents in the run
        )

    async def run(self, request: Any) -> Any:
        # Override with the harness algorithm. Use self.session(agent) to capture agents.
        raise NotImplementedError("Subclass Harness and override run(request), or use HarnessClient.load(implementation=...).")

    async def score(self, request: Any, output: Any) -> float | None:
        # Optional override: return an eval reward label to enrich the trajectory record.
        return None

    # --- run lifecycle -----------------------------------------------------------

    async def execute(self, request: Any, *, timeout_seconds: float | None = None) -> HarnessExecutionResult:
        # Runs one unique execution, then collects a redacted trajectory (consented, fail-open).
        if self._spec is None:
            raise HarnessConfigurationError("Harness.load(...) must be called before execute().")
        timeout = self._validate_timeout(timeout_seconds)
        # Give this execution its own run_id, visible only inside this execution's context,
        # so an overlapping execute() on the same instance cannot overwrite it.
        run_id = f"hrun_{uuid4().hex}"
        token = self._run_id_var.set(run_id)
        self._active_run_ids.append(run_id)
        started_at = _utc_now()
        # Run the author's run(); every failure path finalizes this execution's own manifest.
        try:
            output = await self._invoke_with_timeout(request, timeout)
        except _HarnessDeadlineExpired as exc:
            run = await self._finalize(run_id, request, None, HarnessRunStatus.TIMED_OUT, started_at)
            raise HarnessTimeoutError("Harness execution exceeded timeout_seconds.", run=run) from exc
        except asyncio.CancelledError:
            await self._finalize_shielded(run_id, request, None, HarnessRunStatus.CANCELLED, started_at)
            raise
        except Exception as exc:
            run = await self._finalize(run_id, request, None, HarnessRunStatus.FAILED, started_at)
            raise HarnessExecutionError("Harness implementation execution failed.", run=run) from exc
        finally:
            # The run is over, so session() stops tagging with this run_id.
            self._active_run_ids.remove(run_id)
            self._run_id_var.reset(token)
        # Finalize the successful run with the run_id captured above, not shared state.
        run = await self._finalize(run_id, request, output, HarnessRunStatus.SUCCEEDED, started_at)
        return HarnessExecutionResult(output=output, run=run)

    def _current_run_id(self) -> str | None:
        # Prefers this execution's own run_id; outside any execution context, uses the lone in-flight one.
        run_id = self._run_id_var.get()
        if run_id is not None:
            return run_id
        return self._active_run_ids[0] if len(self._active_run_ids) == 1 else None

    async def _invoke_with_timeout(self, request: Any, timeout_seconds: float | None) -> Any:
        # Applies an optional deadline around the sync-or-async run() override.
        if timeout_seconds is None:
            return await self._invoke(request)
        deadline = asyncio.timeout(timeout_seconds)
        try:
            async with deadline:
                result = await self._invoke(request)
        except TimeoutError as exc:
            if deadline.expired():
                raise _HarnessDeadlineExpired from exc
            raise
        if deadline.expired():
            raise _HarnessDeadlineExpired
        return result

    async def _invoke(self, request: Any) -> Any:
        # Calls the override and awaits only when it returns an awaitable.
        result = self.run(request)
        return await result if inspect.isawaitable(result) else result

    async def _finalize(self, run_id: str, request: Any, output: Any, status: HarnessRunStatus, started_at: str) -> HarnessRun:
        # Builds the operational manifest and runs consented, fail-open collection.
        session_ids = self._safe_session_ids(run_id)
        run = HarnessRun(
            schema_version=HARNESS_SCHEMA_VERSION,
            run_id=run_id,
            spec_id=self.spec.spec_id,
            status=status,
            started_at=started_at,
            ended_at=_utc_now(),
            session_ids=session_ids,
        )
        await self._maybe_collect(run_id, request, output, status)
        return run

    async def _finalize_shielded(self, run_id: str, request: Any, output: Any, status: HarnessRunStatus, started_at: str) -> None:
        # Makes a best-effort, shielded collection attempt before re-raising cancellation.
        task = asyncio.create_task(self._maybe_collect(run_id, request, output, status))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            return

    async def _maybe_collect(self, run_id: str, request: Any, output: Any, status: HarnessRunStatus) -> None:
        # Consent gate + join + sink write. Any failure here must never fail the run.
        if not self._collect or self._sink is None or self._spec is None:
            return
        try:
            reward = await self._safe_score(request, output, status)
            record = TrajectoryCollector(self._store, redactor=self._redactor.redact).collect(
                run_id, self._spec, request, output, status.value, reward=reward
            )
            await self._sink.write(record)
        except Exception:
            return

    async def _safe_score(self, request: Any, output: Any, status: HarnessRunStatus) -> float | None:
        # Requests an optional eval label without letting scoring failures fail collection.
        if status is not HarnessRunStatus.SUCCEEDED:
            return None
        try:
            value = await self.score(request, output)
        except Exception:
            return None
        # @intent non-finite-score-is-no-label
        # A NaN or infinite score is unusable and cannot be JSON-encoded, so it must not cost the run its trajectory.
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

    def _safe_session_ids(self, run_id: str) -> tuple[str, ...]:
        # Reads the fan-in session ids for this run without failing the run on a store error.
        try:
            return tuple(meta.session_id for meta in self._store.list_sessions(tag=run_id))
        except Exception:
            return ()

    def _validate_timeout(self, value: float | None) -> float | None:
        # Requires a positive finite numeric deadline and rejects booleans explicitly.
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0 or value == float("inf") or value != value:
            raise HarnessConfigurationError("timeout_seconds must be a positive finite number or null.", details={"actual_type": type(value).__name__, "value": str(value)})
        return float(value)


def wrap_implementation(implementation: object, *, store: SessionStore | None = None, sink: TrajectorySink | None = None, collect: bool = False, harness_type: str | None = None, harness_version: str | None = None) -> Harness:
    # Adapts a foreign object exposing run(request) into the Harness execution envelope.
    foreign_run = getattr(implementation, "run", None)
    if not callable(foreign_run):
        raise HarnessConfigurationError("Harness implementation must expose callable run(request).", details={"actual_type": type(implementation).__name__})
    resolved_type = str(harness_type if harness_type is not None else getattr(implementation, "type", "") or "")
    resolved_version = str(harness_version if harness_version is not None else getattr(implementation, "version", "") or "")

    class _ForeignHarness(Harness):
        type = resolved_type
        version = resolved_version

        async def run(self, request: Any) -> Any:
            result = foreign_run(request)
            return await result if inspect.isawaitable(result) else result

    return _ForeignHarness(store=store, sink=sink, collect=collect)


__all__ = ["Harness", "wrap_implementation"]
