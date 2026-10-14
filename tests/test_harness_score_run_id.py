"""FILE: tests/test_harness_score_run_id.py

PURPOSE:
    Regression tests for Harness.score() run identity: score() runs inside
    execute(), so self.run_id there is this execution's own run_id. A single
    execute() must not see None, and two overlapping execute() calls on one
    instance must not see each other's run_id when the first one scores.

ROLE IN CODEBASE:
    Exercises vidbyte/harnesses/execution.py, where execute() finalizes a
    successful run (trajectory collection and score()) before it releases
    this execution's run_id.

ARCHITECTURE NOTE:
    Runs offline: run() only sleeps, and an InMemoryTrajectorySink with
    collect=True is required because score() only runs when collection is
    consented.

COMMON MODIFICATION PATTERNS:
    Add further lifecycle cases as harnesses whose score() records
    self.run_id, then compare it with result.run.run_id.

WHAT NOT TO DO IN THIS FILE:
    Do not give both executions the same delay; the bug needs one trial to
    score while the other is still in flight.

KNOWN EDGE CASES:
    After execute() returns, run_id must still be None.

RELATED DOCS: vidbyte/harnesses/README.md
TESTS: python -m pytest tests/test_harness_score_run_id.py
"""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from vidbyte.harnesses import Harness, InMemoryTrajectorySink

CONFIG = {"schema_version": 1, "harness": {"type": "triage"}, "agents": [{"name": "triager"}]}


class _ScoringTriage(Harness):
    type = "triage"
    version = "1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.scored_run_ids: dict[str, str | None] = {}

    async def run(self, request: Any) -> Any:
        run_id = self.run_id
        await asyncio.sleep(request["delay"])   # the shorter trial scores while the longer one is in flight
        return {"q": request["q"], "run_id": run_id}

    async def score(self, request: Any, output: Any) -> float:
        self.scored_run_ids[request["q"]] = self.run_id
        return 1.0


async def _fast_and_slow_trials(harness: Harness) -> list[Any]:
    # Runs two trials concurrently on one instance; the fast one scores while the slow one is in flight.
    return list(await asyncio.gather(harness.execute({"q": "fast", "delay": 0.01}), harness.execute({"q": "slow", "delay": 0.2})))


class HarnessScoreSeesItsOwnRunIdTests(unittest.TestCase):
    def test_single_execute_scores_with_its_own_run_id(self) -> None:
        sink = InMemoryTrajectorySink()
        harness = _ScoringTriage(sink=sink, collect=True).load(CONFIG)

        result = asyncio.run(harness.execute({"q": "A", "delay": 0.0}))

        self.assertEqual(harness.scored_run_ids["A"], result.run.run_id)
        self.assertIsNone(harness.run_id)
        self.assertEqual([(record.run_id, record.reward) for record in sink.records()], [(result.run.run_id, 1.0)])

    def test_overlapping_executions_each_score_with_their_own_run_id(self) -> None:
        sink = InMemoryTrajectorySink()
        harness = _ScoringTriage(sink=sink, collect=True).load(CONFIG)

        fast, slow = asyncio.run(_fast_and_slow_trials(harness))

        self.assertNotEqual(fast.run.run_id, slow.run.run_id)
        self.assertEqual(harness.scored_run_ids, {"fast": fast.run.run_id, "slow": slow.run.run_id})
        self.assertEqual(sorted((record.run_id, record.reward) for record in sink.records()), sorted([(fast.run.run_id, 1.0), (slow.run.run_id, 1.0)]))


if __name__ == "__main__":
    unittest.main()
