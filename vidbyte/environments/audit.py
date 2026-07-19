"""Context Protocol Header

Description:
    Defines the verifier audit kit: scripted adversarial baselines and the
    EnvironmentAudit runner that stress-tests an environment before publication.
Purpose:
    Proves mechanically that a verifier awards nothing to agents that do nothing
    and that repeated verification of identical state is reward-identical, the
    two properties that make rollout data sellable training signal.
Architecture:
    - DoNothingPolicy / EchoPolicy: Model-free baselines that must score ~0.
    - AuditReport: Frozen result carrying baseline scores and determinism.
    - EnvironmentAudit: Orchestrates baselines and the double-verify check.
Relations:
    Uses vidbyte.environments.runner with the opaque-policy path; consumed by
    the EnvironmentsClient namespace.
Similar Files:
    - vidbyte/evals/runner.py: Shares the errors-become-failures philosophy.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from vidbyte.environments.base import Environment
from vidbyte.environments.runner import EnvironmentRunner
from vidbyte.lib.dataclasses.environments import AuditReport


class DoNothingPolicy:
    """Scripted baseline that ends the rollout immediately without acting."""

    async def arun(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        """Return an empty reply without touching any tool or model."""
        del prompt, kwargs
        return SimpleNamespace(output="", calls=(), metadata={})


class EchoPolicy:
    """Scripted baseline that replies with the task instructions verbatim."""

    async def arun(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        """Return the prompt text itself as the entire reply."""
        del kwargs
        return SimpleNamespace(output=prompt, calls=(), metadata={})


class EnvironmentAudit:
    """Runs adversarial baselines and determinism checks against an environment."""

    def __init__(self, environment: Environment, *, max_baseline_score: float = 0.05, n_tasks: int = 3, base_seed: int = 0) -> None:
        # Stores the environment under audit and the pass thresholds.
        self._environment = environment
        self._max_baseline_score = max_baseline_score
        self._n_tasks = max(1, n_tasks)
        self._base_seed = base_seed

    async def arun(self) -> AuditReport:
        """Execute every audit check and fold the outcomes into an AuditReport."""
        notes: list[str] = []
        baseline_scores = await self._run_baselines(notes)
        deterministic = await self._check_determinism(notes)
        ok = deterministic and all(score <= self._max_baseline_score for score in baseline_scores.values())
        return AuditReport(
            env_name=self._environment.name,
            env_version=self._environment.version,
            ok=ok,
            baseline_scores=baseline_scores,
            deterministic=deterministic,
            notes=tuple(notes),
        )

    async def _run_baselines(self, notes: list[str]) -> dict[str, float]:
        # Rolls each scripted baseline over the seeded tasks and records max scores.
        runner = EnvironmentRunner(self._environment, concurrency=1)
        scores: dict[str, float] = {}
        for label, policy in (("do_nothing", DoNothingPolicy()), ("echo", EchoPolicy())):
            worst = 0.0
            for offset in range(self._n_tasks):
                seed = self._base_seed + offset
                record = await runner.arollout(policy, seed=seed)
                worst = max(worst, record.reward.score)
                if record.error is not None:
                    notes.append(f"{label} baseline on seed {seed} errored: {record.error}")
                if record.reward.score > self._max_baseline_score:
                    notes.append(
                        f"{label} baseline scored {record.reward.score:.3f} on seed {seed}, "
                        f"above the {self._max_baseline_score:.3f} threshold."
                    )
            scores[label] = worst
        return scores

    async def _check_determinism(self, notes: list[str]) -> bool:
        # Verifies an identical fresh session twice and requires identical rewards.
        task = self._environment.generator.generate(self._base_seed)
        rewards = []
        for _ in range(2):
            session = self._environment.setup(task)
            try:
                rewards.append(await self._environment.verify(session, ()))
            except Exception as exc:
                notes.append(f"Verifier crashed during determinism check: {exc}")
                return False
            finally:
                self._environment.teardown(session)
        if rewards[0] != rewards[1]:
            notes.append(
                f"Verification is nondeterministic: scores {rewards[0].score:.6f} vs {rewards[1].score:.6f} "
                "for identical sessions."
            )
            return False
        return True


__all__ = [
    "AuditReport",
    "DoNothingPolicy",
    "EchoPolicy",
    "EnvironmentAudit",
]
