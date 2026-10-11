"""FILE: tests/test_harness_execution.py

PURPOSE:
    Regression tests for Harness.execute() run identity: overlapping
    executions on one harness instance each keep their own run_id, tag their
    own sessions with it, and report only those sessions in their manifest.
    A non-finite score() is treated as no label: the trajectory is still
    written to a file sink with reward None.

ROLE IN CODEBASE:
    Exercises vidbyte/harnesses/execution.py, the run lifecycle that assigns a
    run_id, tags self.session(agent) with it, and fans sessions back in by tag.

ARCHITECTURE NOTE:
    Runs offline: an offline test agent is wrapped by self.session(agent), and
    a Session registers its tagged metadata in the store on construction, so
    no model call is needed to observe the fan-in.

COMMON MODIFICATION PATTERNS:
    Add new lifecycle cases (timeout, cancel) as further overlapping-run
    scenarios that assert each manifest names only its own sessions.

WHAT NOT TO DO IN THIS FILE:
    Do not drop the await inside run(); without it the executions never overlap.

KNOWN EDGE CASES:
    After execute() returns, session() must raise and run_id must be None.

RELATED DOCS: vidbyte/harnesses/README.md
TESTS: python -m pytest tests/test_harness_execution.py
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.agent_test_support import build_test_agent
from vidbyte.harnesses import FileTrajectorySink, Harness, HarnessConfigurationError, InMemoryTrajectorySink

CONFIG = {"schema_version": 1, "harness": {"type": "triage"}, "agents": [{"name": "triager"}]}


class _Triage(Harness):
    type = "triage"
    version = "1"

    async def run(self, request: Any) -> Any:
        session = self.session(build_test_agent(name="triager", system_prompt="Triage.", runner=object()))
        await asyncio.sleep(0.01)   # yield so the other execution starts before this one finishes
        return {"session": session.id, "run_id": self.run_id}


class _NonFiniteScoreTriage(_Triage):
    def __init__(self, *args: Any, score_value: float, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._score_value = score_value

    async def score(self, request: Any, output: Any) -> float:
        return self._score_value   # e.g. a mean over an empty set of checks


async def _two_overlapping_trials(harness: Harness) -> list[Any]:
    # Runs two trials concurrently on one harness instance, as an eval fan-out would.
    return list(await asyncio.gather(harness.execute({"q": "A"}), harness.execute({"q": "B"})))


class HarnessOverlappingExecutionTests(unittest.TestCase):
    def test_overlapping_executions_keep_their_own_run_id_and_sessions(self) -> None:
        sink = InMemoryTrajectorySink()
        harness = _Triage(sink=sink, collect=True).load(CONFIG)

        results = asyncio.run(_two_overlapping_trials(harness))

        run_ids = [result.run.run_id for result in results]
        self.assertNotEqual(run_ids[0], run_ids[1])
        for result in results:
            self.assertEqual(result.output["run_id"], result.run.run_id)
            self.assertEqual(result.run.session_ids, (result.output["session"],))
        self.assertEqual(sorted(record.run_id for record in sink.records()), sorted(run_ids))

    def test_session_is_unavailable_after_execute_returns(self) -> None:
        harness = _Triage().load(CONFIG)

        result = asyncio.run(harness.execute({"q": "A"}))

        self.assertTrue(result.run.run_id.startswith("hrun_"))
        self.assertIsNone(harness.run_id)
        with self.assertRaises(HarnessConfigurationError):
            harness.session(build_test_agent(name="late", system_prompt="Late.", runner=object()))


class HarnessNonFiniteScoreTests(unittest.TestCase):
    def test_non_finite_score_keeps_the_trajectory_with_no_reward(self) -> None:
        for score_value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(score=score_value), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "trajectories.jsonl"
                harness = _NonFiniteScoreTriage(sink=FileTrajectorySink(path), collect=True, score_value=score_value).load(CONFIG)

                asyncio.run(harness.execute({"q": "A"}))

                lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
                self.assertEqual(len(lines), 1)
                self.assertIsNone(json.loads(lines[0])["reward"])


if __name__ == "__main__":
    unittest.main()
