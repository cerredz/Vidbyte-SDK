"""FILE: tests/features/harness_compose/test_harness_compose_concurrency.py

PURPOSE: Fan-out, stopping and Grok serialization (AC-10, AC-11, INV-13, INV-14, INV-30, EC-17, EC-20, EC-22): cancelling a composite while a Grok verifier and an opencode verifier hold stops both process trees within the stop bound, removes the worktree, frees the Grok lock and propagates CancelledError unchanged; Grok steps on one workspace never overlap while an opencode step runs beside them; composites on different repositories overlap, composites on the same one do not.
ROLE IN CODEBASE: Start here when a composite leaks a process, a worktree or a Grok lock on cancellation, or when Grok steps collide or wait for each other needlessly.
ARCHITECTURE NOTE: Overlap is proven from the CliRunner spy's enter and exit order, never from a clock. Held stand-ins wait for the sandbox's single release file, which a test writes only after the starts it expects; a start that must not happen is checked with a bounded settle wait, which can let a broken implementation pass on a very slow machine but can never fail a correct one.
FUNCTION INVENTORY: started counts the launches of some labels; finish releases the stand-ins and waits for a task without raising; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Release held stand-ins in a finally block, and wait for the composite before asserting on its record.
WHAT NOT TO DO IN THIS FILE: Do not sleep for a fixed time to wait for a start; poll with wait_until and a deadline.
KNOWN EDGE CASES: A held stand-in ends by itself after its 30-second hold limit, so a broken stop cannot leak it for long. The grandchild of a held stand-in inherits its pipes, so only a whole-tree stop ends it.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-13, INV-14, INV-30, §6.2 AC-10, AC-11, §6.3 EC-17, EC-20, EC-22
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_concurrency.py
"""

from __future__ import annotations

import asyncio

import pytest

SETTLE_SECONDS = 1.5


def started(sandbox, *labels: str) -> list[str]:
    return [launch["label"] for launch in sandbox.launches() if launch["label"] in labels]


async def finish(sandbox, task, timeout: float) -> None:
    # Release every held stand-in and let the composite end, whatever
    # it raises, so no task or process outlives the test.
    sandbox.release()
    await asyncio.wait({task}, timeout=timeout)


@pytest.mark.asyncio
async def test_cancelling_a_verify_stops_both_trees_removes_the_worktree_and_frees_the_lock(compose_api, sandbox, steps, runs, pack, fast_stop, wait_until, alive) -> None:
    # AC-10 / INV-14 / INV-30 / EC-17: CancelledError propagates after
    # both process trees stop, the worktree goes and the Grok lock is
    # free for the next composite.
    api = compose_api
    sandbox.make_repo()
    writer = steps.bind("opencode", label="writer", fake={"write_files": {"feature.txt": "feature\n"}})
    grok = steps.bind("grok", plan=True, label="g-hold", fake={"mode": "hold", "grandchild": True, "text": pack.verdict_json("approve")})
    opencode = steps.bind("opencode", label="oc-hold", fake={"mode": "hold", "grandchild": True, "final_parts": [pack.verdict_json("approve")]})
    task = asyncio.ensure_future(api.compose.verify_with(writer, [grok, opencode], prompt=pack.PROMPT))

    def holding() -> bool:
        launches = [launch for launch in sandbox.launches() if launch["label"] in ("g-hold", "oc-hold")]
        return len(launches) == 2 and all(any(record["kind"] == "grandchild" for record in launch["records"]) for launch in launches)

    try:
        assert await wait_until(holding, pack.WAIT_SECONDS), "both verifiers and their grandchildren started"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            await finish(sandbox, task, pack.WAIT_SECONDS)
    pids = [launch["pid"] for launch in sandbox.launches() if launch["label"] in ("g-hold", "oc-hold")]
    pids += [record["grandchild_pid"] for launch in sandbox.launches() for record in launch["records"] if record["kind"] == "grandchild"]
    assert len(pids) == 4
    assert await wait_until(lambda: not any(alive(pid) for pid in pids), 4 * fast_stop.kill_wait + fast_stop.slack), "every stand-in process tree is stopped"
    assert sandbox.worktrees() == 1 and sandbox.leftovers() == []
    assert sandbox.status() == {"?? feature.txt"}, "the working tree is as the writer left it"
    follow = steps.bind("grok", plan=True, label="follow")
    after = await asyncio.wait_for(api.compose.run_staged_threads([api.records.StageSpec(step=follow, template="Go.")]), 30)
    assert after.failed_stage is None, "the Grok lock for the workspace is free"


@pytest.mark.asyncio
async def test_grok_verifiers_on_one_workspace_take_turns_while_opencode_runs_beside_them(compose_api, sandbox, steps, runs, pack, wait_until) -> None:
    # AC-11 / INV-13 / EC-20: one Grok verifier at a time, the opencode
    # verifier concurrently, all four verdicts recorded.
    api = compose_api
    sandbox.make_repo()
    writer = steps.bind("opencode", label="writer", fake={"write_files": {"feature.txt": "feature\n"}})
    groks = [steps.bind("grok", plan=True, label=f"g{index}", fake={"mode": "hold", "text": pack.verdict_json("approve")}) for index in (1, 2, 3)]
    opencode = steps.bind("opencode", label="oc", fake={"mode": "hold", "final_parts": [pack.verdict_json("approve")]})
    task = asyncio.ensure_future(api.compose.verify_with(writer, [*groks, opencode], prompt=pack.PROMPT))
    try:
        assert await wait_until(lambda: "oc" in started(sandbox, "oc") and len(started(sandbox, "g1", "g2", "g3")) >= 1, pack.WAIT_SECONDS)
        assert not await wait_until(lambda: len(started(sandbox, "g1", "g2", "g3")) >= 2, SETTLE_SECONDS), "a second Grok verifier started while the first held"
    finally:
        await finish(sandbox, task, pack.WAIT_SECONDS)
    result = task.result()
    assert len(result.verdicts) == 4 and all(answer.ok for answer in result.verdicts) and result.agreement is True
    grok_calls = [index for label in ("g1", "g2", "g3") for index in runs.calls_of(label)]
    assert len(grok_calls) == 3
    assert not any(runs.overlap(first, second) for first in grok_calls for second in grok_calls if first < second), "Grok verifiers on one workspace never overlap"
    (opencode_call,) = runs.calls_of("oc")
    assert any(runs.overlap(opencode_call, grok_call) for grok_call in grok_calls), "the opencode verifier runs beside a Grok verifier"


@pytest.mark.asyncio
async def test_composites_serialize_grok_per_workspace_and_overlap_across_repositories(compose_api, sandbox, steps, runs, pack, wait_until) -> None:
    # AC-11 / EC-22 / INV-13: A and C share a workspace and take turns;
    # B on another repository overlaps the one that holds.
    api = compose_api
    other = sandbox.root / "ws-two"
    other.mkdir()
    stage = api.records.StageSpec
    a = steps.bind("grok", plan=True, label="a", fake={"mode": "hold"})
    b = steps.bind("grok", plan=True, label="b", workspace=other, fake={"mode": "hold"})
    c = steps.bind("grok", plan=True, label="c", fake={"mode": "hold"})
    tasks = [asyncio.ensure_future(api.compose.run_staged_threads([stage(step=step, template="Hold.")])) for step in (a, b, c)]
    gathered = asyncio.gather(*tasks, return_exceptions=True)
    try:
        assert await wait_until(lambda: "b" in started(sandbox, "b") and len(started(sandbox, "a", "c")) >= 1, pack.WAIT_SECONDS)
        assert not await wait_until(lambda: len(started(sandbox, "a", "c")) >= 2, SETTLE_SECONDS), "two Grok composites ran at once on one workspace"
    finally:
        await finish(sandbox, gathered, pack.WAIT_SECONDS)
    assert all(task.result().failed_stage is None for task in tasks)
    (a_call,), (b_call,), (c_call,) = runs.calls_of("a"), runs.calls_of("b"), runs.calls_of("c")
    assert not runs.overlap(a_call, c_call), "same workspace: serialized"
    first = a_call if runs.position("enter", a_call) < runs.position("enter", c_call) else c_call
    assert runs.overlap(b_call, first), "different repositories: concurrent"
