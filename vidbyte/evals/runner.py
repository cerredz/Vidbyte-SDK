"""Context Protocol Header

Description:
    Implements EvalRunner, the async-first execution engine for evaluations.
Purpose:
    Executes a collection of evaluation cases against any target (agents or runners)
    with strict concurrency throttling, clean state isolation, and resilient exception handling.
Architecture:
    - EvalRunner: Orchestrates concurrent execution tasks using a Semaphore, isolates stateful agents
      by invoking fork(), and records execution latencies.
Functions:
    - arun: Canonical asynchronous orchestration loop.
    - run: Synchronous wrapper for non-async environments.
    - _run_single_case: Semaphore-guarded single case lifecycle runner.
    - _invoke_target: Dynamic invocation block mapping target execution styles (agents vs. runners).
    - _resolve_model_name: Resolves the descriptor name for the evaluated target entity.
Relations:
    Related to vidbyte.evals.types (receives EvalSuite and outputs EvalSuiteResult) and BaseAgent.
"""

from __future__ import annotations

import time
import inspect
import asyncio
from datetime import datetime
from typing import Any, Sequence
from vidbyte.agents.base import BaseAgent
from vidbyte.evals.types import EvalCase, EvalResult, EvalSuiteResult, GraderResult
from vidbyte.evals.base import BaseGrader


class EvalRunner:
    """Async-first evaluation runner that executes suites against agents or model runners."""

    def __init__(self, target: object, *, default_grader: BaseGrader, concurrency: int = 4, max_retries: int = 1) -> None:
        # Initializes the EvalRunner with an execution target, a default grader, and concurrency settings.
        self.target = target
        self.default_grader = default_grader
        self.concurrency = concurrency
        self.max_retries = max_retries

    async def arun(self, suite: EvalSuite, *, tags: Sequence[str] | None = None) -> EvalSuiteResult:
        # Asynchronously executes the full suite against the target and returns a compiled EvalSuiteResult.
        cases = suite.cases
        if tags:
            target_tags = set(tags)
            cases = tuple(c for c in cases if any(t in target_tags for t in c.tags))

        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [self._run_single_case(case, semaphore) for case in cases]
        results = await asyncio.gather(*tasks)

        model_name = self._resolve_model_name()
        return EvalSuiteResult(
            suite_name=suite.name,
            model=model_name,
            results=tuple(results),
            measured_at=datetime.utcnow()
        )

    def run(self, suite: EvalSuite, *, tags: Sequence[str] | None = None) -> EvalSuiteResult:
        # Synchronously executes the evaluation suite against the target.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(suite, tags=tags))
        if loop.is_running():
            raise RuntimeError("EvalRunner.run() cannot be called from a running event loop; use await arun() instead.")
        return loop.run_until_complete(self.arun(suite, tags=tags))

    async def _run_single_case(self, case: EvalCase, semaphore: asyncio.Semaphore) -> EvalResult:
        # Runs a single evaluation case under the protection of the concurrency semaphore.
        async with semaphore:
            grader = case.grader if case.grader is not None else self.default_grader
            start_time = time.perf_counter()
            actual = ""
            error_msg = None
            metadata = {}

            try:
                actual, metadata = await self._invoke_target(case)
                grader_result = await grader.agrade(case, actual)
            except Exception as exc:
                error_msg = str(exc)
                grader_result = GraderResult(
                    score=0.0,
                    passed=False,
                    reason=f"Execution error: {error_msg}"
                )

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return EvalResult(
                case=case,
                actual=actual,
                grader_result=grader_result,
                latency_ms=latency_ms,
                error=error_msg,
                metadata=metadata
            )

    async def _invoke_target(self, case: EvalCase) -> tuple[str, dict[str, Any]]:
        # Invokes the target execution method (with fork handling for agents) and returns content and metadata.
        target = self.target

        if isinstance(target, BaseAgent):
            forked = target.fork(name=f"{target.name}_eval")
            reply = await forked.arun(case.prompt)
            metadata = dict(reply.metadata) if reply.metadata else {}
            return str(reply.content), metadata

        if hasattr(target, "arun"):
            res = await target.arun(case.prompt)
        elif hasattr(target, "generate_reply"):
            res = await target.generate_reply(case.prompt)
        elif hasattr(target, "run"):
            if inspect.iscoroutinefunction(target.run):
                res = await target.run(case.prompt)
            else:
                res = target.run(case.prompt)
        else:
            raise TypeError("Evaluation target must expose run(), generate_reply(), or arun() method.")

        actual = ""
        if isinstance(res, str):
            actual = res
        elif hasattr(res, "text"):
            actual = str(res.text)
        elif hasattr(res, "content"):
            actual = str(res.content)
        elif isinstance(res, dict) and "text" in res:
            actual = str(res["text"])
        else:
            actual = str(res)

        return actual, {}

    def _resolve_model_name(self) -> str:
        # Resolves a descriptive name for the target representing the evaluated model/provider.
        target = self.target
        if isinstance(target, BaseAgent):
            return target.runner_config.model_name or target.name
        if hasattr(target, "model_name") and getattr(target, "model_name") is not None:
            return str(target.model_name)
        if hasattr(target, "name") and getattr(target, "name") is not None:
            return str(target.name)
        return type(target).__name__
