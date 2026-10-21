"""FILE: tests/features/harness_compose/test_harness_compose_removal.py

PURPOSE: A reader worktree that cannot be removed after its reader answered (EC-16, INV-9, INV-14, INV-15, D-26, spec §17 "The record so far"): when the last verifier's or the last proposer's worktree resists removal, the one WORKTREE_FAILED error names that folder and `git worktree prune`, and its record keeps the writer, or the plan, together with every answer and its thread id, while the selector and the implementer never start; when a sibling verifier is still running at that moment, it is cancelled, its process tree stopped and its worktree removed before the error propagates, no task is left pending, and the record holds the writer alone.
ROLE IN CODEBASE: Start here when a worktree that cannot be deleted loses finished answers, or leaves a sibling, a task or a registration behind.
ARCHITECTURE NOTE: The test keeps the folder from being deleted from outside compose, with the operating system's own rules: on win32 it holds a file open inside the worktree, which Windows will not delete; on POSIX it takes write permission away from a folder inside the worktree, so no entry of it can be unlinked. The hold starts while the reader's stand-in is held, before the test releases it, so the removal that follows the reader's answer is the first one to meet it.
FUNCTION INVENTORY: RemovalBlocker holds and frees one worktree folder; worktree_root finds the compose worktree that holds a launch's working folder; answered_and_removed says whether a worktree reader answered and its worktree went; holder_pids lists a stand-in and its grandchild; task_name names a pending task; settle releases every held stand-in and waits for whatever task a composite left; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Free the blocker in a finally block, so no test leaves an open handle or a read-only folder behind it; RemovalBlocker.free also deletes the folder compose had to leave.
WHAT NOT TO DO IN THIS FILE: Do not mock compose, git or shutil to make the removal fail; hold the folder.
KNOWN EDGE CASES: A process running as root ignores folder permissions, so on POSIX as root these tests skip. The ensemble's failed_stage is a property derived from the record, so a record cut short before the selector reads as SELECT; the tests check the launches instead.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-9, INV-14, INV-15, §6.3 EC-16, §7 D-26, §17; docs/spec/native-thread-compose/review.md R-8
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_removal.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
from pathlib import Path
from typing import IO

import pytest

ROOT_SKIP = "root ignores folder permissions, so no POSIX seam keeps a worktree folder from removal"
THREE = [("ROLE-ONE", "IDENTITY-ONE"), ("ROLE-TWO", "IDENTITY-TWO"), ("ROLE-THREE", "IDENTITY-THREE")]
PROPOSALS = ("PROPOSAL-ONE: lazy imports.", "PROPOSAL-TWO: cache the parser.", "PROPOSAL-THREE: drop plugins.")

pytestmark = pytest.mark.skipif(sys.platform != "win32" and os.geteuid() == 0, reason=ROOT_SKIP)


class RemovalBlocker:
    """Keeps one compose worktree folder from being deleted."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.folder = root / "held-by-test"
        self.handle: IO[str] | None = None

    def hold(self) -> None:
        # Windows deletes no file that a process holds open; POSIX
        # unlinks no entry of a folder without write permission.
        self.folder.mkdir()
        lock = self.folder / "lock.txt"
        lock.write_text("held", encoding="utf-8")
        if sys.platform == "win32":
            self.handle = lock.open("a", encoding="utf-8")
        else:
            self.folder.chmod(0o500)

    def free(self) -> None:
        # Undo the hold, then delete what compose had to leave.
        if self.handle is not None:
            self.handle.close()
        if sys.platform != "win32" and self.folder.exists():
            self.folder.chmod(0o700)
        shutil.rmtree(self.root, ignore_errors=True)


def worktree_root(pack, launch: dict) -> Path:
    folder = Path(launch["start"]["cwd"])
    return next(item for item in (folder, *folder.parents) if item.name.startswith(pack.WORKTREE_PREFIX))


def answered_and_removed(sandbox, pack, label: str) -> bool:
    launches = sandbox.launches(label=label)
    return bool(launches) and pack.launch_answered(launches[0]) and not worktree_root(pack, launches[0]).exists()


def holder_pids(sandbox, label: str) -> list[int]:
    launches = sandbox.launches(label=label)
    pids = [launch["pid"] for launch in launches]
    return pids + [record["grandchild_pid"] for launch in launches for record in launch["records"] if record["kind"] == "grandchild"]


def task_name(task: asyncio.Task) -> str:
    return getattr(task.get_coro(), "__qualname__", None) or task.get_name()


async def settle(sandbox, before: set, timeout: float) -> None:
    # Release every held stand-in and wait for whatever task the
    # composite left, so nothing outlives the test even when it fails.
    sandbox.release()
    left = asyncio.all_tasks() - before
    if left:
        await asyncio.wait(left, timeout=timeout)


@pytest.mark.asyncio
async def test_a_verifier_whose_worktree_cannot_be_removed_keeps_every_verdict(compose_api, sandbox, steps, pack, wait_until, check_compose_error) -> None:
    # EC-16 / INV-15 / D-26 / §17: the Muse verifier answers and its
    # worktree goes; the opencode verifier answers next, but its
    # folder is held. WORKTREE_FAILED names that folder and git
    # worktree prune, and its record keeps the writer and both
    # verdicts with their thread ids. Red until review R-8 lands: the
    # record then held the writer alone.
    api = compose_api
    sandbox.make_repo()
    writer = steps.bind("opencode", label="writer", fake={"write_files": {"feature.txt": "feature\n"}})
    first = steps.bind("muse", label="v-done", fake={"text": pack.verdict_json("approve")})
    last = steps.bind("opencode", label="v-held", fake={"mode": "hold", "final_parts": [pack.verdict_json("reject", findings=["missing test"])]})
    before = asyncio.all_tasks()
    task = asyncio.ensure_future(api.compose.verify_with(writer, [first, last], prompt=pack.PROMPT))
    blocker = None
    try:
        def ready() -> bool:
            return answered_and_removed(sandbox, pack, "v-done") and bool(sandbox.launches(label="v-held"))

        assert await wait_until(ready, pack.WAIT_SECONDS), "the Muse verifier answered and its worktree went while the opencode verifier held"
        blocker = RemovalBlocker(worktree_root(pack, sandbox.only_launch("v-held")))
        blocker.hold()
        sandbox.release()
        with pytest.raises(api.ThreadComposeError) as caught:
            await asyncio.wait_for(task, pack.WAIT_SECONDS)
        registered, leftovers = sandbox.worktrees(), sandbox.leftovers()
    finally:
        if blocker is not None:
            blocker.free()
        await settle(sandbox, before, pack.WAIT_SECONDS)
    error = caught.value
    check_compose_error(error, problem="worktree_failed", workspace=sandbox.workspace, observations=[("folder", pack.path_spellings(blocker.root))])
    assert "git worktree prune" in error.next_step

    # The record keeps the writer and both verdicts, in verifier order.
    record = error.result
    assert isinstance(record, api.records.VerifyResult), f"the record is {record!r}"
    assert record.writer.ok and record.writer.thread_id == pack.launch_session(sandbox.only_launch("writer"))
    sessions = [pack.launch_session(sandbox.only_launch(label)) for label in ("v-done", "v-held")]
    assert [answer.thread_id for answer in record.verdicts] == sessions, "every finished verifier's thread id is kept"
    assert [answer.value.decision.value for answer in record.verdicts] == ["approve", "reject"]
    assert record.verdicts[1].value.findings == ("missing test",)
    assert (registered, leftovers) == (1, [blocker.root.name]), "only the held folder is left, and it is no longer registered"


@pytest.mark.asyncio
async def test_a_proposer_whose_worktree_cannot_be_removed_keeps_the_plan_and_every_proposal(compose_api, sandbox, steps, pack, wait_until, check_compose_error) -> None:
    # EC-16 / INV-15 / D-26 / §17: the Grok fork proposer answers in
    # place, the Muse proposer answers and its worktree goes, and the
    # opencode proposer answers last with its folder held. The record
    # of the one WORKTREE_FAILED keeps the plan and all three
    # proposals with their thread ids; the selector and the
    # implementer never start. Red until review R-8 lands: the record
    # then held the plan alone.
    api = compose_api
    sandbox.make_repo()
    planner = steps.bind("grok", plan=True, label="planner", fake={"text": pack.plan_json(THREE)})
    fork = steps.bind("grok", "fork", plan=True, label="p-grok", fake={"text": PROPOSALS[0]})
    muse = steps.bind("muse", label="p-muse", fake={"text": PROPOSALS[1]})
    held = steps.bind("opencode", label="p-held", fake={"mode": "hold", "final_parts": [PROPOSALS[2]]})
    selector = steps.bind("grok", plan=True, label="selector", fake={"text": pack.selection_json(1, approach="A", rationale="R", guidance="G")})
    implementer = steps.bind("grok", edits=True, label="implementer", fake={"text": "Implemented."})
    roster = api.ensemble.EnsembleRoster(planner=planner, proposers=[fork, muse, held], selector=selector, implementer=implementer)
    before = asyncio.all_tasks()
    task = asyncio.ensure_future(api.compose.run_ensemble(pack.TASK, roster=roster))
    blocker = None
    try:
        def ready() -> bool:
            grok = sandbox.launches(label="p-grok")
            return bool(grok) and pack.launch_answered(grok[0]) and answered_and_removed(sandbox, pack, "p-muse") and bool(sandbox.launches(label="p-held"))

        assert await wait_until(ready, pack.WAIT_SECONDS), "two proposers answered while the opencode proposer held"
        blocker = RemovalBlocker(worktree_root(pack, sandbox.only_launch("p-held")))
        blocker.hold()
        sandbox.release()
        with pytest.raises(api.ThreadComposeError) as caught:
            await asyncio.wait_for(task, pack.WAIT_SECONDS)
        registered, leftovers = sandbox.worktrees(), sandbox.leftovers()
    finally:
        if blocker is not None:
            blocker.free()
        await settle(sandbox, before, pack.WAIT_SECONDS)
    error = caught.value
    check_compose_error(error, problem="worktree_failed", workspace=sandbox.workspace, observations=[("folder", pack.path_spellings(blocker.root))])
    assert "git worktree prune" in error.next_step

    # The record keeps the plan and every proposal, in proposer order.
    record = error.result
    assert isinstance(record, api.ensemble.EnsembleResult), f"the record is {record!r}"
    assert [role.name for role in record.plan.value.roles] == [name for name, _identity in THREE]
    assert [outcome.text for outcome in record.proposals] == list(PROPOSALS)
    sessions = [pack.launch_session(sandbox.only_launch(label)) for label in ("p-grok", "p-muse", "p-held")]
    assert [outcome.thread_id for outcome in record.proposals] == sessions, "every finished proposer's thread id is kept"
    assert record.selection is None and record.implementation is None
    assert sandbox.launches(label="selector") == [] and sandbox.launches(label="implementer") == []
    assert (registered, leftovers) == (1, [blocker.root.name]), "only the held folder is left, and it is no longer registered"


@pytest.mark.asyncio
async def test_a_verifier_whose_worktree_cannot_be_removed_stops_a_running_sibling_first(compose_api, sandbox, steps, pack, fast_stop, wait_until, alive, check_compose_error) -> None:
    # EC-16 / INV-14 / §17: the Muse verifier answers with its folder
    # held while the opencode verifier still runs with a grandchild.
    # The one WORKTREE_FAILED propagates only after that sibling is
    # cancelled: at the raise no task is pending, its process tree is
    # stopped and its worktree removed, well inside the stop bound.
    # The sibling never answered, so the record holds the writer
    # alone (§17: positional verdicts cannot show the gap).
    api = compose_api
    sandbox.make_repo()
    first_release = sandbox.fake_root / "first-release.flag"
    writer = steps.bind("opencode", label="writer", fake={"write_files": {"feature.txt": "feature\n"}})
    first = steps.bind("muse", label="v-first", fake={"mode": "hold", "release_file": str(first_release), "text": pack.verdict_json("approve")})
    running = steps.bind("opencode", label="v-run", fake={"mode": "hold", "grandchild": True, "final_parts": [pack.verdict_json("approve")]})
    before = asyncio.all_tasks()
    task = asyncio.ensure_future(api.compose.verify_with(writer, [first, running], prompt=pack.PROMPT))
    blocker = None
    try:
        def ready() -> bool:
            return bool(sandbox.launches(label="v-first")) and len(holder_pids(sandbox, "v-run")) == 2

        assert await wait_until(ready, pack.WAIT_SECONDS), "both verifiers started and the opencode one has its grandchild"
        sibling_root = worktree_root(pack, sandbox.only_launch("v-run"))
        blocker = RemovalBlocker(worktree_root(pack, sandbox.only_launch("v-first")))
        blocker.hold()
        released = time.monotonic()
        first_release.write_text("go", encoding="utf-8")
        with pytest.raises(api.ThreadComposeError) as caught:
            await asyncio.wait_for(task, pack.WAIT_SECONDS)
        waited = time.monotonic() - released
        pending = sorted(task_name(item) for item in asyncio.all_tasks() - before)
        living = [pid for pid in holder_pids(sandbox, "v-run") if alive(pid)]
        registered, leftovers = sandbox.worktrees(), sandbox.leftovers()
    finally:
        if blocker is not None:
            blocker.free()
        await settle(sandbox, before, pack.WAIT_SECONDS)
    check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, observations=[("folder", pack.path_spellings(blocker.root))])
    assert pack.launch_answered(sandbox.only_launch("v-first")), "the held verifier answered before its removal failed"
    assert pending == [], f"INV-14: tasks still pending when the error propagated: {pending}"
    assert living == [], f"INV-14: the running sibling's processes were alive when the error propagated: {living}"
    assert not sibling_root.exists(), "INV-14: the cancelled sibling's worktree is removed before the error propagates"
    assert (registered, leftovers) == (1, [blocker.root.name])
    assert waited < 4 * fast_stop.kill_wait + fast_stop.slack, f"the error came {waited:.1f} s after the release: the sibling was not cancelled"
    record = caught.value.result
    assert isinstance(record, api.records.VerifyResult) and record.writer.ok and record.verdicts == ()
