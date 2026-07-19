"""Context Protocol Header

Description:
    Defines EnvironmentRunner, which executes seeded rollouts against an
    environment and aggregates calibration reports across harness specs.
Purpose:
    Owns the setup -> build -> run -> verify -> teardown lifecycle with
    guaranteed teardown, error-as-failed-record semantics, and bounded
    concurrency so rollout data stays trustworthy at volume.
Architecture:
    - EnvironmentRunner: arollout / arollout_many / acalibrate orchestration.
Relations:
    Consumes vidbyte.environments.base, resolver, records, and types; used by
    vidbyte.environments.audit and the EnvironmentsClient namespace.
Similar Files:
    - vidbyte/evals/runner.py: Equivalent runner for stateless eval suites.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from vidbyte.environments.base import Environment
from vidbyte.environments.records import RolloutRecorder
from vidbyte.environments.resolver import HarnessSpecResolver
from vidbyte.environments.spec import HarnessSpec
from vidbyte.environments.types import (
    CalibrationCell,
    CalibrationReport,
    EnvSession,
    EnvTask,
    Reward,
    RolloutRecord,
)
from vidbyte.lib.errors import ConfigurationError

_COST_METADATA_KEYS = ("tokens", "input_tokens", "output_tokens", "total_tokens", "cost")


class EnvironmentRunner:
    """Executes seeded rollouts against an environment and records verified outcomes."""

    def __init__(self, environment: Environment, *, recorder: RolloutRecorder | None = None, consent: str = "private", concurrency: int = 2) -> None:
        # Stores the environment, optional recorder, consent level, and concurrency bound.
        if concurrency < 1:
            raise ConfigurationError("EnvironmentRunner concurrency must be at least 1.")
        self._environment = environment
        self._recorder = recorder
        self._consent = consent
        self._concurrency = concurrency
        self._resolver = HarnessSpecResolver(environment)

    async def arollout(self, harness: HarnessSpec | Any, task: EnvTask | None = None, *, seed: int = 0, knobs: Mapping[str, Any] | None = None) -> RolloutRecord:
        """Run one seeded rollout end-to-end and return its verified record."""
        resolved_task = task if task is not None else self._environment.generator.generate(seed, **dict(knobs or {}))
        session = self._setup_session(resolved_task)
        started_at = _utc_now()
        started_clock = time.monotonic()
        error: str | None = None
        try:
            agent, harness_payload = self._resolve_policy(harness, session)
            result, run_error = await self._run_policy(agent, resolved_task)
            error = run_error
            trajectory = self._serialize_trajectory(agent, result)
            reward, verify_error = await self._verify(session, trajectory)
            error = error or verify_error
        finally:
            self._environment.teardown(session)
        record = RolloutRecord(
            env_name=self._environment.name,
            env_version=self._environment.version,
            task=resolved_task,
            harness=harness_payload,
            trajectory=trajectory,
            reward=reward,
            consent=self._consent,
            cost=self._collect_cost(result, started_clock),
            started_at=started_at,
            finished_at=_utc_now(),
            error=error,
        )
        if self._recorder is not None:
            self._recorder.append(record)
        return record

    async def arollout_many(self, harness: HarnessSpec | Any, tasks: Sequence[EnvTask]) -> tuple[RolloutRecord, ...]:
        """Run one rollout per task with bounded concurrency and stable ordering."""
        # Opaque agents share mutable history, so they may not run concurrently.
        if not isinstance(harness, HarnessSpec) and self._concurrency > 1:
            raise ConfigurationError(
                "Prebuilt (opaque) agents require concurrency=1; pass a HarnessSpec for concurrent rollouts."
            )
        semaphore = asyncio.Semaphore(self._concurrency)

        async def _bounded(rollout_task: EnvTask) -> RolloutRecord:
            # Runs one rollout while holding a concurrency slot.
            async with semaphore:
                return await self.arollout(harness, rollout_task)

        return tuple(await asyncio.gather(*(_bounded(item) for item in tasks)))

    async def acalibrate(self, harnesses: Sequence[HarnessSpec], *, n_tasks: int = 10, base_seed: int = 0, knobs: Mapping[str, Any] | None = None) -> CalibrationReport:
        """Run each spec over seeded tasks and fold outcomes into a spec-sheet report."""
        if n_tasks < 1:
            raise ConfigurationError("acalibrate requires n_tasks of at least 1.")
        tasks = tuple(
            self._environment.generator.generate(base_seed + offset, **dict(knobs or {}))
            for offset in range(n_tasks)
        )
        cells: list[CalibrationCell] = []
        for spec in harnesses:
            records = await self.arollout_many(spec, tasks)
            cells.append(self._fold_cell(spec.name, records))
        return CalibrationReport(
            env_name=self._environment.name,
            env_version=self._environment.version,
            cells=tuple(cells),
        )

    def _setup_session(self, task: EnvTask) -> EnvSession:
        # Materializes the session, re-raising setup failures loudly with context.
        try:
            return self._environment.setup(task)
        except Exception as exc:
            raise ConfigurationError(
                f"Environment '{self._environment.name}' setup failed for task '{task.id}': {exc}"
            ) from exc

    def _resolve_policy(self, harness: HarnessSpec | Any, session: EnvSession) -> tuple[Any, dict[str, Any]]:
        # Builds the agent from a spec, or accepts any opaque object exposing arun.
        if isinstance(harness, HarnessSpec):
            return self._resolver.build_agent(harness, session), harness.model_dump()
        if not callable(getattr(harness, "arun", None)):
            raise ConfigurationError("Harness must be a HarnessSpec or expose an async arun(prompt) method.")
        return harness, {"opaque": type(harness).__name__}

    async def _run_policy(self, agent: Any, task: EnvTask) -> tuple[Any, str | None]:
        # Runs the agent on the task instructions, capturing failures as record errors.
        try:
            return await agent.arun(task.instructions), None
        except Exception as exc:
            return None, f"agent_error: {exc}"

    async def _verify(self, session: EnvSession, trajectory: tuple[dict[str, Any], ...]) -> tuple[Reward, str | None]:
        # Scores the final world state, converting verifier crashes into zero rewards.
        try:
            return await self._environment.verify(session, trajectory), None
        except Exception as exc:
            return Reward.failure(str(exc)), f"verifier_error: {exc}"

    def _serialize_trajectory(self, agent: Any, result: Any) -> tuple[dict[str, Any], ...]:
        # Flattens agent history, tool calls, and the final output into JSON-safe steps.
        steps: list[dict[str, Any]] = []
        for message in getattr(agent, "history", ()) or ():
            steps.append(
                {
                    "type": getattr(message, "message_type", "message"),
                    "sender": getattr(message, "sender", ""),
                    "recipient": getattr(message, "recipient", ""),
                    "content": getattr(message, "content", str(message)),
                }
            )
        for call in getattr(result, "calls", ()) or ():
            steps.append({"type": "tool_call", "detail": _jsonable(call)})
        output = getattr(result, "output", None)
        steps.append({"type": "final_output", "content": "" if output is None else str(output)})
        return tuple(steps)

    def _collect_cost(self, result: Any, started_clock: float) -> dict[str, Any]:
        # Extracts normalized cost fields from result metadata plus measured latency.
        cost: dict[str, Any] = {"latency_ms": round((time.monotonic() - started_clock) * 1000.0, 3)}
        metadata = getattr(result, "metadata", None)
        if isinstance(metadata, Mapping):
            for key in _COST_METADATA_KEYS:
                if key in metadata:
                    cost[key] = metadata[key]
        return cost

    def _fold_cell(self, spec_name: str, records: Sequence[RolloutRecord]) -> CalibrationCell:
        # Aggregates records into pass rate, mean score, and per-difficulty pass rates.
        total = len(records)
        pass_rate = sum(1 for record in records if record.reward.passed) / total
        mean_score = sum(record.reward.score for record in records) / total
        by_difficulty: dict[str, list[bool]] = {}
        for record in records:
            label = record.task.difficulty or "unlabeled"
            by_difficulty.setdefault(label, []).append(record.reward.passed)
        difficulty_rates = {
            label: sum(1 for passed in outcomes if passed) / len(outcomes)
            for label, outcomes in by_difficulty.items()
        }
        return CalibrationCell(
            spec_name=spec_name,
            n_rollouts=total,
            pass_rate=pass_rate,
            mean_score=mean_score,
            by_difficulty=difficulty_rates,
        )


def _utc_now() -> str:
    # Returns the current UTC time as an ISO-8601 second-precision string.
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _jsonable(value: Any) -> Any:
    # Converts dataclasses to dicts and everything else to strings for JSON safety.
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


__all__ = [
    "EnvironmentRunner",
]
