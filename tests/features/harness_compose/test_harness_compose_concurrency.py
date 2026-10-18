"""FILE: tests/features/harness_compose/test_harness_compose_concurrency.py

PURPOSE: Fan-out, stopping and Grok serialization (AC-10, AC-11, INV-13, INV-14, INV-30, EC-17, EC-19, EC-20, EC-22): cancelling a composite while a Grok verifier and an opencode verifier hold stops both process trees within the stop bound, removes the worktree, frees the Grok lock and propagates CancelledError unchanged; a verifier whose worktree cannot be added cancels its sibling, and its one WORKTREE_FAILED propagates only after every sibling has stopped and cleaned up; Grok steps on one workspace never overlap while an opencode step runs beside them; composites on different repositories overlap, composites on the same one do not.
ROLE IN CODEBASE: Start here when a composite leaks a process, a task, a worktree or a Grok lock on cancellation or on a sibling's failure, or when Grok steps collide or wait for each other needlessly.
ARCHITECTURE NOTE: Overlap is proven from the CliRunner spy's enter and exit order, never from a clock. Held stand-ins wait for the sandbox's single release file, which a test writes only after the starts it expects; a start that must not happen is checked with a bounded settle wait, which can let a broken implementation pass on a very slow machine but can never fail a correct one. A fan-out child is made to fail from outside compose through the sandbox repository's own reference-transaction hook, which git runs during worktree add (spec EC-59, T-6): the hook fails the add only once the scene it waits for is in place, so the failure always lands while the sibling holds.
FUNCTION INVENTORY: started counts the launches of some labels; finish releases the stand-ins and waits for a task without raising; plant_add_gate installs the hook that fails worktree adds on cue; removal_seconds times this machine's git for the removal that follows a failed add; gate_failures reads when, and after what wait, the hook failed each add; holder_pids lists a held stand-in's process and its grandchild; task_name names a pending task; settle releases the stand-ins and waits for every task a composite left; the test_* functions are one behaviour each.
COMMON MODIFICATION PATTERNS: Release held stand-ins in a finally block, and wait for the composite before asserting on its record. To check the state at the moment an error propagates, read it right after the raise and before any await.
WHAT NOT TO DO IN THIS FILE: Do not sleep for a fixed time to wait for a start; poll with wait_until and a deadline. Do not mock compose or git to make a child fail; plant the hook.
KNOWN EDGE CASES: A held stand-in ends by itself after its 30-second hold limit, so a broken stop cannot leak it for long. The grandchild of a held stand-in inherits its pipes, so only a whole-tree stop ends it. A reference-transaction hook that exits 1 when the add's transaction is prepared makes git print "ref updates aborted by hook" (git 2.53 and earlier) or "in 'prepared' phase, update aborted by the reference-transaction hook" (git 2.54 and later), exit 128 and remove the new folder and its registration itself; worktree remove runs no such hook. The hook waits at most GATE_BOUND_SECONDS for its cue and then fails the add anyway, recording that it timed out. Two adds that fail must be staggered by less than one removal's time for the second verifier to be mid-removal when the first one's error arrives, so that case sweeps the stagger across the measured window in STAGGER_STEPS runs and fails on the first run that leaves a task behind.
RELATED DOCS: tests/features/harness_compose/FEATURE.md; docs/spec/native-thread-compose/spec.md §6.1 INV-9, INV-13, INV-14, INV-30, §6.2 AC-10, AC-11, §6.3 EC-17, EC-19, EC-20, EC-22, EC-59; docs/spec/native-thread-compose/review.md R-10, R-16
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/test_harness_compose_concurrency.py
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import pytest

SETTLE_SECONDS = 1.5
GATE_BOUND_SECONDS = 20.0
STAGGER_STEPS = 5
GATE_SCRIPT = """import json
import sys
import time
from pathlib import Path


def cue_met(config, number):
    claims = Path(config["claims"])
    if number and not (claims / f"failed-{number - 1:03d}").exists():
        return False
    if len(list(claims.glob("claim-*"))) < config["arrivals"]:
        return False
    grandchildren = 0
    for log in Path(config["log_dir"]).glob("*.jsonl"):
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("kind") == "grandchild":
                grandchildren += 1
    return grandchildren >= config["grandchildren"]


def main(state):
    sys.stdin.read()
    if state != "prepared":
        return 0
    config = json.loads(Path(CONFIG).read_text(encoding="utf-8"))
    number = 0
    while True:
        try:
            Path(config["claims"], f"claim-{number:03d}").open("x").close()
            break
        except FileExistsError:
            number += 1
    deadline = time.monotonic() + config["bound"]
    while not cue_met(config, number) and time.monotonic() < deadline:
        time.sleep(0.005)
    outcome = "cue" if cue_met(config, number) else "timed out"
    if number:
        time.sleep(config["stagger"])
    record = {"at": time.time(), "outcome": outcome}
    Path(config["claims"], f"failed-{number:03d}").write_text(json.dumps(record), encoding="utf-8")
    return 1


sys.exit(main(sys.argv[1]))
"""


def started(sandbox, *labels: str) -> list[str]:
    return [launch["label"] for launch in sandbox.launches() if launch["label"] in labels]


async def finish(sandbox, task, timeout: float) -> None:
    # Release every held stand-in and let the composite end, whatever
    # it raises, so no task or process outlives the test.
    sandbox.release()
    await asyncio.wait({task}, timeout=timeout)


def plant_add_gate(sandbox, pack, *, arrivals: int = 1, grandchildren: int = 0, stagger: float = 0.0, name: str = "add-gate") -> Path:
    # Every worktree add in the sandbox repository waits until
    # `arrivals` adds have reached the hook and the stand-in logs hold
    # `grandchildren` grandchild records, then fails (EC-59: compose's
    # git still runs the hook). A later add also waits for the one
    # before it to fail, and then `stagger` seconds more.
    #
    # The repository's own core.hooksPath names the hook's folder by an
    # absolute path: git for Windows cannot start a hook named by a
    # relative path, nor find sh on the sandbox's closed PATH, so the
    # hook is an .exe built as Sandbox.stand_in builds one, and a
    # script on POSIX.
    gate = sandbox.root / name
    claims, hooks = gate / "claims", gate / "hooks"
    for folder in (claims, hooks):
        folder.mkdir(parents=True)
    config = gate / "config.json"
    settings = {"claims": str(claims), "log_dir": str(sandbox.log_dir), "arrivals": arrivals, "grandchildren": grandchildren, "stagger": stagger, "bound": GATE_BOUND_SECONDS}
    config.write_text(json.dumps(settings), encoding="utf-8")
    body = f"CONFIG = {str(config)!r}\n{GATE_SCRIPT}"
    if sys.platform == "win32":
        launcher = pack.launcher_bytes()
        if launcher is None:
            pytest.skip("pip's console-script launcher (distlib t64.exe) is needed to build an .exe hook")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("__main__.py", body)
        (hooks / "reference-transaction.exe").write_bytes(launcher + f'#!"{sys.executable}"\r\n'.encode("utf-8") + archive.getvalue())
    else:
        hook = hooks / "reference-transaction"
        hook.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        hook.chmod(0o755)
    sandbox.git("config", "core.hooksPath", hooks.as_posix())
    return claims


def removal_seconds(sandbox) -> float:
    # The median time this machine's git takes for the removal compose
    # runs after a failed add: a worktree remove of a folder git never
    # registered, which git refuses after its start-up work.
    durations = []
    for _ in range(3):
        began = time.perf_counter()
        sandbox.git("worktree", "remove", "--force", str(sandbox.root / "never-added"), check=False)
        durations.append(time.perf_counter() - began)
    return sorted(durations)[1]


def gate_failures(claims: Path) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(claims.glob("failed-*"))]


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
async def test_a_failed_worktree_add_stops_the_holding_sibling_before_its_error_propagates(compose_api, sandbox, steps, pack, fast_stop, alive, check_compose_error) -> None:
    # INV-14 / EC-19 / EC-17 / INV-9 / INV-30: the opencode verifier's
    # worktree add fails while the Grok verifier holds in place with a
    # grandchild. Its one WORKTREE_FAILED propagates only after the
    # Grok verifier is cancelled and its process tree stopped: at the
    # raise no task is pending, no stand-in process is alive, only the
    # main worktree is registered and no folder is left, and the raise
    # comes within the stop bound, long before the 30 s hold limit.
    api = compose_api
    sandbox.make_repo()
    claims = plant_add_gate(sandbox, pack, grandchildren=1)
    writer = steps.bind("opencode", label="writer", fake={"write_files": {"feature.txt": "feature\n"}})
    grok = steps.bind("grok", plan=True, label="g-hold", fake={"mode": "hold", "grandchild": True, "text": pack.verdict_json("approve")})
    opencode = steps.bind("opencode", label="oc-add", fake={"final_parts": [pack.verdict_json("approve")]})
    before = asyncio.all_tasks()
    try:
        with pytest.raises(api.ThreadComposeError) as caught:
            await api.compose.verify_with(writer, [grok, opencode], prompt=pack.PROMPT)
        raised_at = time.time()
        pending = sorted(task_name(task) for task in asyncio.all_tasks() - before)
        pids = holder_pids(sandbox, "g-hold")
        living = [pid for pid in pids if alive(pid)]
        registered, leftovers = sandbox.worktrees(), sandbox.leftovers()
    finally:
        await settle(sandbox, before, pack.WAIT_SECONDS)
    failures = gate_failures(claims)
    assert [failure["outcome"] for failure in failures] == ["cue"], "the add failed once, while the Grok verifier held with its grandchild"
    check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by")
    assert len(pids) == 2, "the Grok verifier and its grandchild were running"
    assert sandbox.launches(label="oc-add") == [], "the verifier without a worktree never starts"
    assert pending == [], f"INV-14: tasks still pending when the error propagated: {pending}"
    assert living == [], f"INV-14 / INV-30: stand-in processes alive when the error propagated: {living}"
    assert (registered, leftovers) == (1, []), f"EC-17: {registered} worktrees registered and {leftovers} left when the error propagated"
    waited = raised_at - failures[0]["at"]
    assert waited < 4 * fast_stop.kill_wait + fast_stop.slack, f"the error propagated {waited:.1f} s after the add failed: the sibling was not cancelled"


@pytest.mark.asyncio
async def test_two_failed_worktree_adds_propagate_one_error_after_both_cleanups_end(compose_api, sandbox, steps, pack, check_compose_error) -> None:
    # INV-14 / EC-19 / EC-17: both opencode verifiers' worktree adds
    # fail, the second one a fraction of a removal's time after the
    # first, so the first verifier's error arrives while the second
    # verifier is still removing its worktree. One WORKTREE_FAILED
    # propagates, never an ExceptionGroup, and only once that
    # cancelled sibling's removal has ended: no task is pending at the
    # raise. Red until review R-10 lands: a cancel there ends the wait
    # on the shielded removal, which still runs when the error goes.
    api = compose_api
    sandbox.make_repo()
    # The window is about one removal wide, so time this machine's git
    # for the removal compose runs after a failed add, and sweep the
    # stagger across that window instead of trusting one guess.
    removal = removal_seconds(sandbox)
    for step in range(1, STAGGER_STEPS + 1):
        stagger = removal * step / (STAGGER_STEPS + 1)
        claims = plant_add_gate(sandbox, pack, arrivals=2, stagger=stagger, name=f"add-gate-{step}")
        writer = steps.bind("opencode", label=f"writer-{step}", fake={"write_files": {f"feature-{step}.txt": "feature\n"}})
        first = steps.bind("opencode", label=f"oc-add-{step}-a", fake={"final_parts": [pack.verdict_json("approve")]})
        second = steps.bind("opencode", label=f"oc-add-{step}-b", fake={"final_parts": [pack.verdict_json("approve")]})
        before = asyncio.all_tasks()
        try:
            with pytest.raises(api.ThreadComposeError) as caught:
                await api.compose.verify_with(writer, [first, second], prompt=pack.PROMPT)
            pending = sorted(task_name(task) for task in asyncio.all_tasks() - before)
            registered, leftovers = sandbox.worktrees(), sandbox.leftovers()
        finally:
            await settle(sandbox, before, pack.WAIT_SECONDS)
        assert [failure["outcome"] for failure in gate_failures(claims)] == ["cue", "cue"], "both adds were held until both had arrived, then failed"
        check_compose_error(caught.value, problem="worktree_failed", workspace=sandbox.workspace, git_text="aborted by")
        assert sandbox.launches(label=f"oc-add-{step}-a") == [] and sandbox.launches(label=f"oc-add-{step}-b") == []
        assert pending == [], f"INV-14: with the second add failing {stagger * 1000:.0f} ms after the first, tasks were still pending when the error propagated: {pending}"
        assert (registered, leftovers) == (1, []), f"EC-17: {registered} worktrees registered and {leftovers} left when the error propagated"


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
